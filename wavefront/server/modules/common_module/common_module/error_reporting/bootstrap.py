"""Sentry error reporting for Wavefront services: errors only, next to OTel.

OpenTelemetry stays the only tracer (``common_module/telemetry``, which must
not import any vendor SDK). Sentry receives errors, each linked to the active
OTel trace id, and creates no spans of its own and no propagation headers.

``sentry_sdk`` is imported only inside this package, and only once a DSN is
configured, so services without one never load it.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Sequence

from common_module.error_reporting import scrubbing, throttle
from common_module.error_reporting.settings import ErrorReportingSettings
from common_module.log.logger import logger

# Top-level package of every workspace member. Frames from these are marked
# in-app. A test compares this with the wheel packages on disk.
WORKSPACE_PACKAGES: list[str] = [
    'agents_module',
    'api_services_module',
    'auth_module',
    'authenticator',
    'call_processing',
    'celery_worker',
    'chatbots_module',
    'common_module',
    'datasource',
    'db_repo_module',
    'deprecated_api_module',
    'floconsole',
    'floware',
    'flo_cloud',
    'flo_lib',
    'flo_stream',
    'flo_testing',
    'flo_utils',
    'guardrails_module',
    'inference_app',
    'knowledge_base_module',
    'llm_inference_config_module',
    'mailer',
    'plugins_module',
    'product_analysis_module',
    'rag_ingestion',
    'tools_module',
    'triggers_module',
    'user_management_module',
    'voice_agents_module',
]

FRAMEWORKS = ('fastapi', 'celery')

_lock = threading.Lock()
# None until the first configure call; then that call's result.
_configured: bool | None = None
# The settings Sentry was started with; None unless it started.
_active_settings: ErrorReportingSettings | None = None


def error_reporting_enabled() -> bool:
    """True after a successful init in this process."""
    return _configured is True


def active_settings() -> ErrorReportingSettings | None:
    """The settings Sentry was started with, or None when it is not running."""
    return _active_settings


def configure_error_reporting(
    settings: ErrorReportingSettings,
    *,
    frameworks: Sequence[str] = (),
    _transport: Any = None,
) -> bool:
    """Initialise Sentry for this process. Never raises.

    ``frameworks`` names the integrations the service needs, from
    ``FRAMEWORKS``. Returns True when Sentry was initialised, False when it is
    disabled (no DSN) or failed to start. Only the first call in a process does
    anything; later calls return its result.

    ``_transport`` is for tests only.
    """
    global _configured, _active_settings
    with _lock:
        if _configured is None:
            _configured = _configure(settings, frameworks, _transport)
            if _configured:
                _active_settings = settings
        return _configured


def shutdown_error_reporting(timeout: float = 2.0) -> None:
    """Send pending events, waiting at most ``timeout`` seconds.

    Blocking, bounded by ``timeout``. Call it from shutdown code once serving
    has stopped, like ``shutdown_telemetry()``; never from a request path. This
    is the flush that counts: uvicorn re-raises SIGTERM after shutdown, so the
    SDK's own flush at interpreter exit does not run then. The client is left
    open, so errors raised later in shutdown are still captured. Safe when
    never configured.
    """
    if not error_reporting_enabled():
        return
    try:
        import sentry_sdk

        sentry_sdk.get_client().flush(timeout=timeout)
    except Exception as exc:
        logger.warning(f'Flushing Sentry events failed: {type(exc).__name__}: {exc}')


def _configure(
    settings: ErrorReportingSettings,
    frameworks: Sequence[str],
    transport: Any,
) -> bool:
    try:
        if not settings.dsn:
            logger.info('Sentry error reporting disabled: no DSN configured')
            return False

        import sentry_sdk
        from sentry_sdk.integrations.argv import ArgvIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration, ignore_logger
        from sentry_sdk.integrations.modules import ModulesIntegration
        from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber

        logging_integration = LoggingIntegration(
            level=settings.breadcrumb_level,
            event_level=logging.ERROR,
            # Never ship log lines to Sentry Logs; events and breadcrumbs only.
            sentry_logs_level=None,
        )
        _throttle_log_events(logging_integration, settings.max_events_per_minute)
        integrations: list[Any] = [logging_integration]
        otlp = _otlp_integration()
        if otlp is not None:
            integrations.append(otlp)
        integrations.extend(_framework_integrations(frameworks))

        options: dict[str, Any] = {
            'dsn': settings.dsn,
            'environment': settings.environment,
            'release': settings.release,
            'sample_rate': settings.sample_rate,
            'default_integrations': True,
            # The default would switch on about 20 integrations, OpenAI,
            # Anthropic, httpx, SQLAlchemy and Redis among them.
            'auto_enabling_integrations': False,
            # Argv: the command line adds nothing and could hold secrets.
            # Modules: scans every installed package on the first event, on
            # the event loop (about 250 ms), to list versions nobody reads.
            'disabled_integrations': [ArgvIntegration(), ModulesIntegration()],
            # Errors only: no per-request session (release health) envelopes.
            'auto_session_tracking': False,
            'integrations': integrations,
            # No `sentry-trace` or `baggage` headers on outbound requests.
            'trace_propagation_targets': [],
            'send_default_pii': False,
            # Locals hold prompts, documents and tokens.
            'include_local_variables': False,
            'max_request_body_size': 'never',
            # Cap every string in an event; also bounds what scrubbing sees.
            'max_value_length': 4096,
            'attach_stacktrace': False,
            'event_scrubber': EventScrubber(
                denylist=DEFAULT_DENYLIST + scrubbing.EXTRA_DENYLIST,
                recursive=True,
            ),
            'before_send': scrubbing.before_send,
            'before_breadcrumb': scrubbing.before_breadcrumb,
            'in_app_include': WORKSPACE_PACKAGES,
        }
        if transport is not None:
            options['transport'] = transport

        # Access lines carry the full request line (query string included) and
        # the client address; they would become breadcrumbs at INFO.
        ignore_logger('uvicorn.access')
        # OTel's own failures (a collector that is down) log at ERROR on every
        # export attempt: that is a telemetry outage, not an application error.
        ignore_logger('opentelemetry*')
        # Before init, so no event can go out without it.
        sentry_sdk.get_global_scope().set_tag('service', settings.service_name)
        sentry_sdk.init(**options)
    except Exception as exc:
        logger.warning(
            f'Sentry error reporting not started: {type(exc).__name__}: {exc}'
        )
        return False

    logger.info(
        f'Sentry error reporting enabled for {settings.service_name} '
        f'(environment {settings.environment})'
    )
    return True


def _throttle_log_events(logging_integration: Any, per_minute: int) -> None:
    """Drop excess error logs before the SDK turns them into events.

    The SDK's event handler is a plain ``logging.Handler``, so a filter on it
    runs before any event is built. If a future SDK renames it, events are
    still capped in ``before_send``, only later.
    """
    throttle.configure(per_minute)
    handler = getattr(logging_integration, '_handler', None)
    if isinstance(handler, logging.Handler):
        handler.addFilter(throttle.LogThrottleFilter())
    else:
        logger.warning(
            'Sentry log events are capped only after they are built: '
            'the SDK has no event handler to filter'
        )


def _otlp_integration() -> Any:
    """Links events to the active OTel trace, without exporting or propagating.

    With both flags off the integration only registers a lookup of the current
    OTel span; it adds no span processor and leaves the global propagator as
    the telemetry bootstrap set it.
    """
    try:
        from sentry_sdk.integrations.otlp import OTLPIntegration

        return OTLPIntegration(
            setup_otlp_traces_exporter=False,
            setup_propagator=False,
        )
    except Exception as exc:
        logger.warning(
            f'Sentry events will not be linked to OTel traces: '
            f'{type(exc).__name__}: {exc}'
        )
        return None


def _framework_integrations(frameworks: Sequence[str]) -> list[Any]:
    if isinstance(frameworks, str):
        frameworks = (frameworks,)
    integrations: list[Any] = []
    for name in frameworks:
        try:
            if name == 'fastapi':
                from sentry_sdk.integrations.fastapi import FastApiIntegration
                from sentry_sdk.integrations.starlette import StarletteIntegration

                # Events are named after the route template (`/users/{id}`),
                # which scrubbing uses in place of the raw path.
                integrations += [
                    StarletteIntegration(transaction_style='url'),
                    FastApiIntegration(transaction_style='url'),
                ]
            elif name == 'celery':
                from sentry_sdk.integrations.celery import CeleryIntegration

                integrations.append(
                    # No Sentry headers on task messages; no cron monitors.
                    CeleryIntegration(propagate_traces=False, monitor_beat_tasks=False)
                )
            else:
                logger.warning(
                    f'Unknown error-reporting framework {name!r}; expected one '
                    f'of {FRAMEWORKS}. Skipped.'
                )
        except Exception as exc:
            logger.warning(
                f'Sentry {name} integration not enabled: {type(exc).__name__}: {exc}'
            )
    return integrations


def _reset_for_tests() -> None:
    """Close the client and forget the configure result. Tests only."""
    global _configured, _active_settings
    with _lock:
        _configured = None
        _active_settings = None
        throttle.reset()
        try:
            import sentry_sdk

            sentry_sdk.get_client().close(timeout=0)
            for scope in (
                sentry_sdk.get_current_scope(),
                sentry_sdk.get_isolation_scope(),
                sentry_sdk.get_global_scope(),
            ):
                scope.clear()
            sentry_sdk.get_global_scope().set_client(None)
        except ImportError:
            pass
