"""Immutable, app-wide runtime settings built from an app's config.ini.

``CommonContainer.runtime_settings`` builds one ``RuntimeSettings`` from the
running app's config; apps hand that object (or the fields they need) to the
components they build. There is no process-wide copy.

Field defaults here only describe the *unconfigured* state and are chosen to be
safe (``production``, localhost). The deployed defaults live in config.ini.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class RuntimeSettings:
    app_env: str = 'production'
    floware_base_url: str = 'http://localhost:8001'
    passthrough_secret: str | None = None
    call_processing_base_url: str | None = None
    allowed_origins: tuple[str, ...] = ('http://localhost:5173',)
    worker_count: int = 4
    uvicorn_log_level: str = 'critical'

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> RuntimeSettings:
        """Build from an app config mapping.

        Reads ``[env_config]`` (``app_env``, ``base_url``, ``passthrough_secret``,
        ``worker_count``, ``uvicorn_log_level``), ``[web] allowed_origins`` and
        ``[voice_agents] call_processing_base_url``. Missing or empty values fall
        back to the dataclass defaults.
        """

        def value(section: str, key: str) -> Any:
            return (config.get(section) or {}).get(key) or None

        raw: dict[str, Any] = {
            'app_env': value('env_config', 'app_env'),
            'floware_base_url': value('env_config', 'base_url'),
            'passthrough_secret': value('env_config', 'passthrough_secret'),
            'call_processing_base_url': value(
                'voice_agents', 'call_processing_base_url'
            ),
            'allowed_origins': value('web', 'allowed_origins'),
            'worker_count': value('env_config', 'worker_count'),
            'uvicorn_log_level': value('env_config', 'uvicorn_log_level'),
        }
        kwargs = {k: v for k, v in raw.items() if v is not None}

        if 'floware_base_url' in kwargs:
            kwargs['floware_base_url'] = kwargs['floware_base_url'].rstrip('/')
        if 'allowed_origins' in kwargs:
            kwargs['allowed_origins'] = tuple(
                origin.strip()
                for origin in kwargs['allowed_origins'].split(',')
                if origin.strip()
            )
        if 'worker_count' in kwargs:
            kwargs['worker_count'] = int(kwargs['worker_count'])
        return cls(**kwargs)
