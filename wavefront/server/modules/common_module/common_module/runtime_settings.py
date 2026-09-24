"""Process-wide settings populated from the running app's config.ini.

Call ``configure_runtime_settings`` once at startup (floware, celery, workflow
job, etc.) before any code that reads these values.
"""

from __future__ import annotations

floware_base_url: str = 'http://localhost:8001'
passthrough_secret: str | None = None
call_processing_base_url: str | None = None
allowed_origins: str = 'http://localhost:5173'
app_env: str = 'production'
worker_count: int = 4
uvicorn_log_level: str = 'critical'


def configure_runtime_settings(
    *,
    floware_base_url: str | None = None,
    passthrough_secret: str | None = None,
    call_processing_base_url: str | None = None,
    allowed_origins: str | None = None,
    app_env: str | None = None,
    worker_count: int | str | None = None,
    uvicorn_log_level: str | None = None,
) -> None:
    """Overwrite module defaults from app config. Omit a kwarg to leave it unchanged."""
    import common_module.runtime_settings as settings

    if floware_base_url is not None:
        settings.floware_base_url = floware_base_url.rstrip('/')
    if passthrough_secret is not None:
        settings.passthrough_secret = passthrough_secret or None
    if call_processing_base_url is not None:
        settings.call_processing_base_url = call_processing_base_url or None
    if allowed_origins is not None:
        settings.allowed_origins = allowed_origins
    if app_env is not None:
        settings.app_env = app_env
    if worker_count is not None:
        settings.worker_count = int(worker_count)
    if uvicorn_log_level is not None:
        settings.uvicorn_log_level = uvicorn_log_level
