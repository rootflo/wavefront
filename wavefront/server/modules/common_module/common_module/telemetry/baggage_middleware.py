from typing import Any, Dict

from opentelemetry import baggage
from opentelemetry import context
from opentelemetry import trace

from common_module.middleware.request_id_middleware import get_current_request_id

# Custom domain attributes use the `app.` prefix so they never collide with
# OpenTelemetry semantic conventions.
USER_ID_KEY = 'app.user.id'
ROLE_ID_KEY = 'app.role.id'
SESSION_ID_KEY = 'app.session.id'
REQUEST_ID_KEY = 'app.request.id'

_SESSION_FIELDS = (
    ('user_id', USER_ID_KEY),
    ('role_id', ROLE_ID_KEY),
    ('session_id', SESSION_ID_KEY),
)


class BaggageMiddleware:
    """Puts multi-tenant / business context into OpenTelemetry Baggage.

    Values are read from the authenticated ``UserSession`` that
    ``RequireAuthMiddleware`` places on the request, plus the request ID, so no
    caller has to send additional headers for this to work.

    This is deliberately raw ASGI middleware rather than ``BaseHTTPMiddleware``:
    the latter runs the downstream app in a separate anyio task with a *copied*
    context, so a ``context.attach()`` performed inside it does not reliably
    reach the route handlers. A raw ASGI middleware attaches on the same
    coroutine, so the baggage is visible to every span created downstream.

    Must be registered so it runs *inside* ``RequireAuthMiddleware`` and
    ``RequestIdMiddleware`` (i.e. added to the app before them), and *inside*
    the FastAPI instrumentation, so the SERVER span is already open and can be
    annotated directly.

    Note that ``app.user.id`` is carried in the clear here on purpose: the local
    Jaeger pipeline keeps it for debugging, and the collector hashes it before
    anything is exported to a cloud backend.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get('type') != 'http':
            await self.app(scope, receive, send)
            return

        entries = self._collect(scope)
        if not entries:
            await self.app(scope, receive, send)
            return

        ctx = context.get_current()
        for key, value in entries.items():
            ctx = baggage.set_baggage(key, value, context=ctx)

        # The SERVER span is already open (the OTel ASGI middleware sits further
        # out), so it predates this baggage and BaggageSpanProcessor cannot see
        # it. Annotate it directly; child spans inherit via the processor.
        span = trace.get_current_span()
        if span.is_recording():
            for key, value in entries.items():
                span.set_attribute(key, value)

        token = context.attach(ctx)
        try:
            await self.app(scope, receive, send)
        finally:
            context.detach(token)

    @staticmethod
    def _collect(scope: Dict[str, Any]) -> Dict[str, str]:
        entries: Dict[str, str] = {}

        # `request.state` is backed by `scope['state']`, so the session that
        # RequireAuthMiddleware assigned is readable here without a Request.
        session = (scope.get('state') or {}).get('session')
        if session is not None:
            for attribute, key in _SESSION_FIELDS:
                value = getattr(session, attribute, None)
                if value:
                    entries[key] = str(value)

        request_id = get_current_request_id()
        if request_id and request_id != 'NO-REQUEST-ID':
            entries[REQUEST_ID_KEY] = request_id

        return entries
