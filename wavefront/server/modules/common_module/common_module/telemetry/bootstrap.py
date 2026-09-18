"""Vendor-agnostic OpenTelemetry bootstrap for Wavefront services.

Only ``opentelemetry-api`` / ``opentelemetry-sdk`` and the official
``opentelemetry-instrumentation-*`` packages are used here. No cloud vendor SDK
(Azure Monitor, AWS X-Ray, Datadog, ...) is ever imported into application code:
fan-out, sampling, PII redaction and backend authentication all live in the
OpenTelemetry Collector. Switching APM backends is therefore a collector
configuration change with no application rebuild.

Every service speaks plain OTLP to the collector and nothing else.
"""

import os
import socket
from typing import Any, Dict, Optional

from opentelemetry import trace
from opentelemetry.propagate import set_global_textmap
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from common_module.log.logger import logger
from common_module.telemetry.baggage_span_processor import BaggageSpanProcessor

# Endpoints that generate telemetry noise without diagnostic value. Matched as
# regexes against the request URL by the FastAPI instrumentation.
EXCLUDED_URLS = 'health,healthz,docs,openapi.json,redoc,favicon.ico'

_providers_configured = False
_sqlalchemy_instrumented = False


def telemetry_endpoint() -> Optional[str]:
    """Return the collector endpoint, or ``None`` when telemetry is disabled."""
    return os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT') or None


def _service_name(default: str) -> str:
    return os.getenv('OTEL_SERVICE_NAME') or os.getenv('APP_NAME') or default


def _resource_attributes() -> Dict[str, Any]:
    """Extra resource attributes beyond service name/version/environment.

    ``service.instance.id`` lets a backend tell replicas apart. It replaces the
    per-request client-IP ``instance`` label the old Prometheus middleware used,
    which was both unbounded in cardinality and personally identifying.
    """
    instance_id = os.getenv('HOSTNAME') or socket.gethostname()
    return {
        'service.instance.id': f'{instance_id}:{os.getpid()}',
    }


def _rebuild_flo_ai_metric_singletons() -> None:
    """Re-create flo_ai's metric holders now that a MeterProvider exists.

    ``flo_ai.telemetry.instrumentation`` builds ``llm_metrics``, ``agent_metrics``
    and ``workflow_metrics`` at import time, and each constructor calls
    ``get_meter()`` — which returns ``None`` until ``configure_telemetry()`` has
    run. Every ``record_*`` call then short-circuits, so LLM/agent/workflow
    metrics are silently never emitted.

    Import ordering cannot avoid this: ``flo_ai/__init__.py`` pulls the
    instrumentation module in transitively, so those constructors have already
    run before any ``configure_telemetry`` call is reachable. Rebuilding the
    module-level singletons afterwards works because the decorators resolve them
    as module globals at call time.

    The real fix is lazy meter resolution inside flo_ai; remove this once a
    flo-ai release carries it.
    """
    try:
        import flo_ai.telemetry.instrumentation as instrumentation

        instrumentation.llm_metrics = instrumentation.LLMMetrics()
        instrumentation.agent_metrics = instrumentation.AgentMetrics()
        instrumentation.workflow_metrics = instrumentation.WorkflowMetrics()
    except Exception as exc:
        logger.error(
            f'Could not rebuild flo_ai metric instruments; LLM/agent metrics '
            f'will not be emitted: {exc}',
            exc_info=True,
        )


def _restrict_propagation() -> None:
    """Keep W3C trace context on the wire, and drop baggage.

    OpenTelemetry defaults ``OTEL_PROPAGATORS`` to ``tracecontext,baggage``, so
    every request the httpx instrumentation injects into would carry a
    ``baggage`` header. ``BaggageMiddleware`` puts ``app.user.id``,
    ``app.role.id`` and ``app.session.id`` on the context, and the LLM clients
    (OpenAI, Anthropic, Azure OpenAI) are all httpx-based — so those
    authenticated identifiers would travel to third-party APIs on every model
    call. The collector-side hashing protects the *export* path only; it can do
    nothing about a header we send ourselves.

    Nothing here consumes propagated baggage: the sole reader is
    ``BaggageSpanProcessor``, which takes it off the in-process context rather
    than the header. Dropping the baggage propagator therefore costs no
    observability — ``traceparent`` still goes out, so distributed traces stay
    connected — and it additionally stops an untrusted caller from spoofing
    ``app.*`` baggage into our spans.

    Called unconditionally, before the collector-endpoint check: baggage is
    attached to the context by middleware that runs even with telemetry
    switched off, so the wire format must be locked down either way rather
    than relying on no other library ever calling ``propagate.inject()``.
    """
    set_global_textmap(TraceContextTextMapPropagator())


def configure_telemetry_providers(default_service_name: str) -> bool:
    """Set up trace/metric providers and library instrumentation.

    Returns ``True`` when telemetry was configured, ``False`` when it is
    disabled because no collector endpoint is set. Never raises: a broken
    telemetry setup must not stop a service from serving traffic.
    """
    global _providers_configured

    # First, and on every path: BaggageMiddleware populates the context whether
    # or not telemetry is enabled, so the baggage propagator has to go even when
    # we bail out below. Idempotent, so repeat calls are harmless.
    _restrict_propagation()

    if _providers_configured:
        return True

    otlp_endpoint = telemetry_endpoint()
    if not otlp_endpoint:
        logger.info('OTEL_EXPORTER_OTLP_ENDPOINT is not set; OpenTelemetry is disabled')
        return False

    service_name = _service_name(default_service_name)

    try:
        from flo_ai import configure_telemetry

        configure_telemetry(
            service_name=service_name,
            service_version=os.getenv('APP_VERSION', '0.1.0'),
            environment=os.getenv('APP_ENV', 'dev'),
            otlp_endpoint=otlp_endpoint,
            additional_attributes=_resource_attributes(),
        )
        _rebuild_flo_ai_metric_singletons()

        # flo_ai installs its TracerProvider as the global one, so the baggage
        # processor can be attached to it after the fact.
        tracer_provider = trace.get_tracer_provider()
        if hasattr(tracer_provider, 'add_span_processor'):
            tracer_provider.add_span_processor(BaggageSpanProcessor())

        _instrument_clients()

        _providers_configured = True
        logger.info(
            f'OpenTelemetry configured for service "{service_name}" '
            f'(env={os.getenv("APP_ENV", "dev")}) exporting to {otlp_endpoint}'
        )
        return True
    except Exception as exc:
        logger.error(f'Failed to initialize OpenTelemetry: {exc}', exc_info=True)
        return False


def _instrument_clients() -> None:
    """Instrument outbound clients so their spans join the request trace."""
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
    except Exception as exc:
        logger.warning(f'Redis instrumentation unavailable: {exc}')

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except Exception as exc:
        logger.warning(f'HTTPX instrumentation unavailable: {exc}')


def instrument_fastapi(app: Any) -> None:
    """Attach the OpenTelemetry ASGI middleware to a FastAPI app.

    Call this *after* every other ``add_middleware`` call. Starlette inserts
    middleware at position 0, so the last one registered is the outermost — and
    the SERVER span should wrap auth, security headers and CORS rather than
    starting inside them.

    This is the only source of HTTP spans and HTTP metrics. It emits standard
    semantic conventions and route-template span names, and extracts inbound
    trace context from request headers, so no hand-written HTTP middleware is
    needed or wanted alongside it.

    The "already done" check is per app object, never a module-level flag.
    ``python server.py`` executes the server module up to three times in one
    process tree - as ``__main__``, as ``__mp_main__`` in uvicorn's spawned
    reload/worker child, and again as ``server`` when uvicorn imports the
    ``"server:app"`` string - and each execution builds a *different* FastAPI
    instance. Only the last one is served. A process-global flag is set by the
    first instance and silently skips the one that actually handles requests,
    which costs every HTTP SERVER span while leaving the redis/httpx/SQLAlchemy
    spans (global monkey-patches, not per-app) working - so telemetry looks
    half-alive rather than broken.
    """
    if not _providers_configured:
        return

    # Set by FastAPIInstrumentor itself; instrumenting twice only warns, but
    # checking keeps the log honest.
    if getattr(app, '_is_instrumented_by_opentelemetry', False):
        return

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        # `exclude_spans` drops the per-ASGI-event `http send` / `http receive`
        # INTERNAL spans. They restate timings the SERVER span already carries,
        # but there are three or more of them per request - the majority of
        # every request trace, and the part that grows fastest with traffic.
        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls=EXCLUDED_URLS,
            exclude_spans=['receive', 'send'],
        )
        logger.info(f'FastAPI instrumentation enabled (app id={id(app):#x})')
    except Exception as exc:
        logger.error(f'Failed to instrument FastAPI app: {exc}', exc_info=True)


def instrument_sqlalchemy(engine: Any) -> None:
    """Instrument a SQLAlchemy engine so queries appear as ``db.*`` spans.

    ``engine`` is expected to be an ``AsyncEngine``. The instrumentation must be
    given the underlying *sync* engine — handing it an ``AsyncEngine`` directly
    silently produces no spans.
    """
    global _sqlalchemy_instrumented

    if _sqlalchemy_instrumented or not _providers_configured or engine is None:
        return

    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(
            engine=getattr(engine, 'sync_engine', engine)
        )
        _sqlalchemy_instrumented = True
        logger.info('SQLAlchemy instrumentation enabled')
    except Exception as exc:
        logger.warning(f'SQLAlchemy instrumentation unavailable: {exc}')


def shutdown_telemetry() -> None:
    """Flush and shut down the telemetry providers.

    Safe to call unconditionally; call it from a ``finally`` so buffered spans
    and metrics are not lost when shutdown takes an error path.
    """
    if not _providers_configured:
        return

    try:
        from flo_ai import shutdown_telemetry as flo_shutdown

        flo_shutdown()
        logger.info('OpenTelemetry providers shut down')
    except Exception as exc:
        logger.warning(f'Error shutting down OpenTelemetry: {exc}')
