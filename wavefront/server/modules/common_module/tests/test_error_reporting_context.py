"""ErrorReportingContextMiddleware: request id and identity on Sentry events.

The app below mirrors floware's middleware order:
fake auth (sets request.state.session) -> RequestIdMiddleware -> context.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.middleware import _MiddlewareFactory
from starlette.middleware.base import BaseHTTPMiddleware

from common_module.error_reporting import ErrorReportingContextMiddleware, bootstrap
from common_module.error_reporting import context
from common_module.error_reporting.context import hash_user_id
from common_module.log.logger import logger
from common_module.middleware.request_id_middleware import RequestIdMiddleware

USER_ID = '6f1c2a9e-3b7d-4c55-9a10-2f4e8d7b1c33'
REQUEST_ID = 'fe-abcd1234'


@dataclass
class _Session:
    role_id: str
    user_id: str
    session_id: str


class _FakeAuth(BaseHTTPMiddleware):
    """Stands in for RequireAuthMiddleware: a session for /user/* paths."""

    async def dispatch(self, request, call_next):
        if request.url.path.startswith('/user/'):
            request.state.session = _Session(
                role_id='editor', user_id=USER_ID, session_id='session-secret'
            )
        return await call_next(request)


def _app(global_handler: bool = False) -> FastAPI:
    app = FastAPI()
    # Last added runs first: auth -> request id -> context (innermost).
    for middleware in (ErrorReportingContextMiddleware, RequestIdMiddleware, _FakeAuth):
        app.add_middleware(cast(_MiddlewareFactory[Any], middleware))

    # Like floware's global handler: swallow, log at error, answer 500. An
    # `Exception` handler runs in ServerErrorMiddleware, outside every user
    # middleware, which is the path floware takes.
    if global_handler:

        @app.exception_handler(Exception)
        async def handled(request: Request, exc: Exception):
            logger.error('handled failure')
            return JSONResponse(status_code=500, content={'error': 'x'})

    @app.get('/user/unhandled')
    async def user_unhandled():
        raise RuntimeError('unhandled')

    @app.get('/user/handled')
    async def user_handled():
        raise ValueError('handled')

    @app.get('/anon/unhandled')
    async def anon_unhandled():
        raise RuntimeError('anonymous')

    @app.get('/user/ok')
    async def user_ok():
        return {}

    return app


def _runtime_data(event: dict) -> str:
    """The event as JSON without the source lines Sentry quotes around frames
    (our own code, which here contains the literals being searched for)."""
    event = json.loads(json.dumps(event))
    for exception in (event.get('exception') or {}).get('values', []):
        for frame in (exception.get('stacktrace') or {}).get('frames', []):
            for key in ('pre_context', 'context_line', 'post_context'):
                frame.pop(key, None)
    return json.dumps(event)


def _get(path: str, global_handler: bool = False):
    client = TestClient(_app(global_handler), raise_server_exceptions=False)
    return client.get(path, headers={'X-Flo-Request-ID': REQUEST_ID})


def test_unhandled_exception_carries_request_and_identity(start_sentry):
    transport = start_sentry(frameworks=('fastapi',))
    _get('/user/unhandled')

    (event,) = transport.events
    assert event['tags']['request_id'] == REQUEST_ID
    assert event['tags']['role_id'] == 'editor'
    assert event['user'] == {'id': hash_user_id(USER_ID)}
    serialized = _runtime_data(event)
    assert USER_ID not in serialized
    assert 'session-secret' not in serialized


def test_error_logged_by_an_exception_handler_carries_context(start_sentry):
    transport = start_sentry(frameworks=('fastapi',))
    _get('/user/handled', global_handler=True)

    (event,) = transport.events
    assert event['tags']['request_id'] == REQUEST_ID
    assert event['user'] == {'id': hash_user_id(USER_ID)}


def test_unauthenticated_request_has_no_identity(start_sentry):
    transport = start_sentry(frameworks=('fastapi',))
    _get('/anon/unhandled')

    (event,) = transport.events
    assert event['tags']['request_id'] == REQUEST_ID
    assert 'role_id' not in event['tags']
    assert 'user' not in event


def test_context_does_not_leak_into_the_next_request(start_sentry):
    transport = start_sentry(frameworks=('fastapi',))
    client = TestClient(_app(), raise_server_exceptions=False)
    client.get('/user/ok', headers={'X-Flo-Request-ID': REQUEST_ID})
    client.get('/anon/unhandled', headers={'X-Flo-Request-ID': 'fe-zzzz9999'})

    (event,) = transport.events
    assert event['tags']['request_id'] == 'fe-zzzz9999'
    assert 'user' not in event
    assert 'role_id' not in event['tags']


def test_middleware_passes_through_when_sentry_is_off():
    bootstrap._reset_for_tests()
    response = TestClient(_app()).get('/user/ok')
    assert response.status_code == 200


def test_no_context_without_the_starlette_integration(start_sentry):
    # Without Sentry's per-request scope, tags would carry over between
    # requests, so the middleware sets none.
    transport = start_sentry()
    client = TestClient(_app(), raise_server_exceptions=False)
    client.get('/user/ok', headers={'X-Flo-Request-ID': REQUEST_ID})
    logger.error('outside any request')

    (event,) = transport.events
    assert 'user' not in event
    assert 'role_id' not in event['tags']
    assert event['tags'].get('request_id') != REQUEST_ID


def test_a_tagging_failure_does_not_break_the_request(
    start_sentry, monkeypatch, caplog
):
    start_sentry(frameworks=('fastapi',))

    def broken(user_id):
        raise RuntimeError('hash broke')

    monkeypatch.setattr(context, 'hash_user_id', broken)
    response = TestClient(_app()).get('/user/ok')

    assert response.status_code == 200
    assert 'Could not set Sentry request context' in caplog.text


def test_user_id_hash_is_stable_and_not_the_id():
    assert hash_user_id(USER_ID) == hash_user_id(USER_ID)
    assert hash_user_id(USER_ID) != hash_user_id(USER_ID.replace('6', '7'))
    assert USER_ID not in hash_user_id(USER_ID)
    assert len(hash_user_id(USER_ID)) == 16
