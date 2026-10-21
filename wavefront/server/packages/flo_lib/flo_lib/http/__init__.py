"""HTTP client surface backed by httpx2.

Call sites import from here instead of httpx, requests, or aiohttp.
Applications that still have dependencies importing ``httpx`` should call
``alias_httpx()`` at process startup, before those imports.
"""

from httpx2 import (
    ASGITransport,
    AsyncClient,
    BasicAuth,
    Client,
    ConnectError,
    ConnectTimeout,
    HTTPError,
    HTTPStatusError,
    Limits,
    MockTransport,
    ReadTimeout,
    RemoteProtocolError,
    Request,
    RequestError,
    Response,
    Timeout,
    TimeoutException,
    USE_CLIENT_DEFAULT,
    alias_httpx,
    get,
    post,
    request,
)

from flo_lib.http.client import create_async_client, create_client

__all__ = [
    'ASGITransport',
    'AsyncClient',
    'BasicAuth',
    'Client',
    'ConnectError',
    'ConnectTimeout',
    'HTTPError',
    'HTTPStatusError',
    'Limits',
    'MockTransport',
    'ReadTimeout',
    'RemoteProtocolError',
    'Request',
    'RequestError',
    'Response',
    'Timeout',
    'TimeoutException',
    'USE_CLIENT_DEFAULT',
    'alias_httpx',
    'create_async_client',
    'create_client',
    'get',
    'post',
    'request',
]
