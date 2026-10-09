"""Client factories with a shared default timeout."""

from httpx2 import AsyncClient, Client

DEFAULT_TIMEOUT_SECONDS = 30.0


def create_client(**kwargs) -> Client:
    """Sync client. ``timeout`` defaults to 30s; pass ``timeout=`` to override."""
    kwargs.setdefault('timeout', DEFAULT_TIMEOUT_SECONDS)
    return Client(**kwargs)


def create_async_client(**kwargs) -> AsyncClient:
    """Async client. ``timeout`` defaults to 30s; pass ``timeout=`` to override."""
    kwargs.setdefault('timeout', DEFAULT_TIMEOUT_SECONDS)
    return AsyncClient(**kwargs)
