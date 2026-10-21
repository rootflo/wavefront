"""Callables and resource hooks for ``ApplicationContainer`` providers."""

from __future__ import annotations

import socket

from common_module.config_loader import is_truthy
from common_module.log.logger import configure_logging


def scheduler_worker_id(configured: str) -> str:
    return (configured or '').strip() or socket.gethostname()


def guardrails_mode(enabled: str | None) -> str:
    return 'on' if is_truthy(enabled) else 'off'


def guardrails_engine(selected):
    """The engine when guardrails are on, else None. Lazy: the engine builds on call."""
    if selected is None:
        return None
    return selected.guardrails_engine()


def start_logging(app_name: str, log_level: str) -> None:
    configure_logging(app_name=app_name, log_level=log_level)


def start_telemetry(config: dict) -> None:
    from common_module.telemetry import TelemetrySettings
    from common_module.telemetry import configure_telemetry_providers

    configure_telemetry_providers(
        TelemetrySettings.from_config(
            config, default_service_name=config['env_config']['app_name']
        )
    )


def start_presidio_timeout(timeout: str | None) -> None:
    """Presidio reads REGEX_TIMEOUT_SECONDS at import. Set it before that import."""
    from guardrails_module.bootstrap import start_presidio_regex_timeout

    start_presidio_regex_timeout(timeout)
