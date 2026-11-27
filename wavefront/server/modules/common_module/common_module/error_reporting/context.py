"""Per-request context on Sentry events: request id, hashed user id, role.

``ErrorReportingContextMiddleware`` copies who and what a request is onto
Sentry's per-request scope, so every event from that request carries it,
unhandled exceptions included. The request-id context variable alone is not
enough there: the request-id middleware has already reset it by the time the
framework reports an unhandled exception.

The user id is sent only as a hash. It still groups events by user ("affected
users") without storing the raw id in Sentry. The session id is not sent.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict

from common_module.error_reporting import bootstrap
from common_module.log.logger import logger
from common_module.middleware.request_id_middleware import get_current_request_id

_NO_REQUEST_ID = 'NO-REQUEST-ID'


def hash_user_id(user_id: str) -> str:
    """A stable, non-reversible stand-in for a user id (ids are UUIDs)."""
    return hashlib.sha256(user_id.encode()).hexdigest()[:16]


class ErrorReportingContextMiddleware:
    """Raw ASGI middleware, like ``BaggageMiddleware``.

    Register it inside ``RequireAuthMiddleware`` and ``RequestIdMiddleware`` so
    the session and request id are already set. Does nothing unless error
    reporting was started.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if (
            scope.get('type') in ('http', 'websocket')
            and bootstrap.error_reporting_enabled()
        ):
            _tag_request(scope)
        await self.app(scope, receive, send)


def _tag_request(scope: Dict[str, Any]) -> None:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.starlette import StarletteIntegration

        # Sentry's Starlette integration opens one isolation scope per request,
        # so these values reach only this request's events. Without it the
        # scope is shared, and tags would carry over to the next request.
        if sentry_sdk.get_client().get_integration(StarletteIntegration) is None:
            return
        sentry_scope = sentry_sdk.get_isolation_scope()

        request_id = get_current_request_id()
        if request_id and request_id != _NO_REQUEST_ID:
            sentry_scope.set_tag('request_id', request_id)

        # `request.state` is backed by `scope['state']`.
        session = (scope.get('state') or {}).get('session')
        user_id = getattr(session, 'user_id', None)
        if user_id:
            sentry_scope.set_user({'id': hash_user_id(str(user_id))})
        role_id = getattr(session, 'role_id', None)
        if role_id:
            sentry_scope.set_tag('role_id', str(role_id))
    except Exception as exc:
        # Context is a nice-to-have; the request must go on regardless.
        logger.warning(f'Could not set Sentry request context: {type(exc).__name__}')
