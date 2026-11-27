"""warm_guardrails loads models at worker start, on the shared event loop."""

from unittest.mock import AsyncMock, MagicMock, patch

import celery_worker.services as services
import celery_worker.settings as settings
import celery_worker.signals as signals
from celery_worker.event_loop import close_event_loop


def _config(enabled: str) -> dict:
    return {**settings.CONFIG, 'guardrails': {'enabled': enabled}}


def teardown_function():
    close_event_loop()


def test_warmup_runs_engine_warmup_when_enabled():
    engine = MagicMock()
    engine.warmup = AsyncMock()
    worker = MagicMock(guardrails_engine=engine)

    with (
        patch.object(settings, 'CONFIG', _config('true')),
        patch.object(services, 'get_services', return_value=worker),
    ):
        signals.warm_guardrails()

    engine.warmup.assert_awaited_once()


def test_warmup_skips_building_services_when_disabled():
    with (
        patch.object(settings, 'CONFIG', _config('false')),
        patch.object(services, 'get_services') as get_services,
    ):
        signals.warm_guardrails()

    get_services.assert_not_called()


def test_warmup_tolerates_missing_engine():
    worker = MagicMock(guardrails_engine=None)

    with (
        patch.object(settings, 'CONFIG', _config('true')),
        patch.object(services, 'get_services', return_value=worker),
    ):
        signals.warm_guardrails()


def test_warmup_failure_is_logged_not_raised():
    with (
        patch.object(settings, 'CONFIG', _config('true')),
        patch.object(
            services, 'get_services', side_effect=RuntimeError('model download failed')
        ),
        patch('common_module.log.logger.logger.exception') as log_exception,
    ):
        signals.warm_guardrails()

    log_exception.assert_called_once()
