"""Immutable, app-wide runtime settings built from an app's config.ini.

``CommonContainer.runtime_settings`` builds one ``RuntimeSettings`` from the
running app's config; apps hand that object (or the fields they need) to the
components they build. There is no process-wide copy.

Deployed defaults live in config.ini. This class does not repeat them:
``from_config`` raises when a required key is missing or empty.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class RuntimeSettingsError(ValueError):
    pass


def _required(config: Mapping[str, Any], section: str, key: str) -> str:
    raw = (config.get(section) or {}).get(key)
    if raw is None or str(raw).strip() == '':
        raise RuntimeSettingsError(
            f'[{section}] {key} is required in config.ini (set the env var or a :default)'
        )
    return str(raw)


def _optional(config: Mapping[str, Any], section: str, key: str) -> str | None:
    raw = (config.get(section) or {}).get(key)
    if raw is None or str(raw).strip() == '':
        return None
    return str(raw)


@dataclass(frozen=True)
class RuntimeSettings:
    app_env: str
    floware_base_url: str
    allowed_origins: tuple[str, ...]
    worker_count: int
    uvicorn_log_level: str
    passthrough_secret: str | None = None
    call_processing_base_url: str | None = None

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> RuntimeSettings:
        """Build from an app config mapping."""
        origins = tuple(
            origin.strip()
            for origin in _required(config, 'web', 'allowed_origins').split(',')
            if origin.strip()
        )
        if not origins:
            raise RuntimeSettingsError(
                '[web] allowed_origins is required in config.ini'
            )
        return cls(
            app_env=_required(config, 'env_config', 'app_env'),
            floware_base_url=_required(config, 'env_config', 'base_url').rstrip('/'),
            passthrough_secret=_optional(config, 'env_config', 'passthrough_secret'),
            call_processing_base_url=_optional(
                config, 'voice_agents', 'call_processing_base_url'
            ),
            allowed_origins=origins,
            worker_count=int(_required(config, 'env_config', 'worker_count')),
            uvicorn_log_level=_required(config, 'env_config', 'uvicorn_log_level'),
        )
