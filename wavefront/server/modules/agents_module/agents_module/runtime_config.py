"""Process settings for agents that are not passed through every constructor."""

_celery_broker_url: str | None = None
_azure_openai_api_version: str | None = None


def configure_celery_broker(broker_url: str) -> None:
    global _celery_broker_url
    _celery_broker_url = broker_url


def get_celery_broker_url() -> str:
    if not _celery_broker_url:
        raise RuntimeError(
            'Celery broker is not configured; call configure_celery_broker '
            'from the app startup that loads config.ini'
        )
    return _celery_broker_url


def configure_azure_openai_api_version(api_version: str | None) -> None:
    global _azure_openai_api_version
    _azure_openai_api_version = api_version or None


def get_azure_openai_api_version() -> str | None:
    return _azure_openai_api_version
