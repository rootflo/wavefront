import httpx2

from flo_lib.http import (
    AsyncClient,
    Client,
    HTTPError,
    HTTPStatusError,
    create_async_client,
    create_client,
)
from flo_lib.http.client import DEFAULT_TIMEOUT_SECONDS


def test_create_client_uses_default_timeout():
    client = create_client()
    try:
        assert client.timeout.connect == DEFAULT_TIMEOUT_SECONDS
    finally:
        client.close()


def test_create_client_honors_explicit_timeout():
    client = create_client(timeout=5.0)
    try:
        assert client.timeout.connect == 5.0
    finally:
        client.close()


async def test_create_async_client_uses_default_timeout():
    client = create_async_client()
    try:
        assert isinstance(client, AsyncClient)
        assert client.timeout.connect == DEFAULT_TIMEOUT_SECONDS
    finally:
        await client.aclose()


def test_reexports_are_httpx2_types():
    assert Client is httpx2.Client
    assert AsyncClient is httpx2.AsyncClient
    assert HTTPStatusError is httpx2.HTTPStatusError
    assert issubclass(HTTPStatusError, HTTPError)
