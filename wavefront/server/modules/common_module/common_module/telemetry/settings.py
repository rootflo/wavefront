"""OpenTelemetry settings built from an app's config.ini."""

from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class TelemetrySettings:
    service_name: str
    app_env: str = 'dev'
    app_version: str = '0.1.0'
    otlp_endpoint: str | None = None
    instance_id: str | None = None

    @classmethod
    def from_config(
        cls,
        config: Mapping[str, Any],
        *,
        default_service_name: str,
    ) -> TelemetrySettings:
        env = config.get('env_config') or {}
        telemetry = config.get('telemetry') or {}
        endpoint = telemetry.get('otlp_endpoint') or None
        if endpoint == '':
            endpoint = None
        instance = telemetry.get('instance_id') or None
        if instance == '':
            instance = None
        return cls(
            service_name=telemetry.get('service_name') or default_service_name,
            app_env=env.get('app_env') or 'dev',
            app_version=telemetry.get('app_version') or '0.1.0',
            otlp_endpoint=endpoint,
            instance_id=instance,
        )

    def resolved_instance_id(self) -> str:
        host = self.instance_id or socket.gethostname()
        return f'{host}'
