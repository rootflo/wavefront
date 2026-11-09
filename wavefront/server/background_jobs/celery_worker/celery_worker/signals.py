"""Celery worker process signals (telemetry, guardrails warmup, event-loop teardown)."""

from celery.signals import (
    worker_process_init,
    worker_process_shutdown,
    worker_shutdown,
)


@worker_process_init.connect
def setup_telemetry(**kwargs):
    """Configure OpenTelemetry once per worker process, before any task runs.

    Previously this lived inside `get_services()` and only ran when the first
    task built services, so anything before that — and any code path that
    doesn't go through `get_services()` — was untraced. Doing it here, at
    process start, covers the whole worker lifetime.
    """
    from common_module.telemetry import TelemetrySettings, configure_telemetry_providers
    from celery_worker.settings import CONFIG

    configure_telemetry_providers(
        TelemetrySettings.from_config(
            CONFIG, default_service_name='wavefront-celery-worker'
        )
    )


@worker_process_init.connect
def warm_guardrails(**kwargs):
    """Load the guardrails models before any task runs, as floware does at startup.

    Services are otherwise built by the first task, so the spaCy download and
    load landed inside that task's per-check timeout and, under a FAIL_CLOSED
    policy, rejected it. Connected after setup_telemetry so the work is traced.
    Runs on the shared loop so the adapters' async clients bind to the loop
    tasks use. A failure is logged, not raised: the first task retries.
    """
    from common_module.config_loader import is_truthy
    from common_module.log.logger import logger
    from celery_worker.settings import CONFIG

    if not is_truthy(CONFIG.get('guardrails', {}).get('enabled')):
        return

    from celery_worker.event_loop import get_event_loop
    from celery_worker.services import get_services

    try:
        engine = get_services().guardrails_engine
        if engine is not None:
            logger.info('Warming up guardrails engines and models...')
            get_event_loop().run_until_complete(engine.warmup())
    except Exception:
        logger.exception(
            'Guardrails warmup failed; the first guarded task will load models instead'
        )


def teardown_event_loop(**kwargs):
    from celery_worker.event_loop import close_event_loop

    close_event_loop()


def teardown_telemetry(**kwargs):
    from common_module.telemetry import shutdown_telemetry

    shutdown_telemetry()


# Only the prefork pool dispatches worker_process_shutdown (celery/concurrency/
# prefork.py) — under solo it never fires, and solo is where the loop lives in
# the main process. Hook the worker-level signal too, which fires for every
# pool. close_event_loop() is idempotent, so a double-fire is harmless.
worker_process_shutdown.connect(teardown_event_loop, weak=False)
worker_shutdown.connect(teardown_event_loop, weak=False)

# Same prefork-vs-solo split as above, connected after the event-loop teardown
# so any pending async work has already wound down. shutdown_telemetry() is
# safe to call unconditionally (a no-op if telemetry was never configured), so
# a double-fire across both signals is harmless.
worker_process_shutdown.connect(teardown_telemetry, weak=False)
worker_shutdown.connect(teardown_telemetry, weak=False)
