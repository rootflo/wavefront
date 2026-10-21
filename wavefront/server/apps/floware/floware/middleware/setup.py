from collections.abc import Sequence
from typing import Any, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware import _MiddlewareFactory

from common_module.middleware.request_id_middleware import RequestIdMiddleware
from common_module.middleware.security_headers import SecurityHeadersMiddleware
from common_module.runtime_settings import RuntimeSettings
from common_module.telemetry import BaggageMiddleware, instrument_fastapi
from user_management_module.authorization.require_auth import RequireAuthMiddleware


def _middleware(cls: type[Any]) -> _MiddlewareFactory[Any]:
    return cast(_MiddlewareFactory[Any], cls)


def add_middlewares(
    app: FastAPI,
    *,
    runtime: RuntimeSettings,
    hmac_routes: Sequence[str],
    mtls_allowed_namespaces: Sequence[str],
) -> None:
    # Order matters: last added runs first on incoming requests, so execution
    # order (outer -> inner) here is:
    #   OTel -> CORS -> SecurityHeaders -> RequireAuth -> RequestId -> Baggage
    # BaggageMiddleware is added first (innermost) so it runs after
    # RequireAuthMiddleware has set request.state.session and RequestIdMiddleware
    # has set the request-id context var.
    app.add_middleware(_middleware(BaggageMiddleware))
    app.add_middleware(_middleware(RequestIdMiddleware))
    app.add_middleware(
        _middleware(RequireAuthMiddleware),
        app_env=runtime.app_env,
        passthrough_secret=runtime.passthrough_secret,
        hmac_routes=hmac_routes,
        mtls_allowed_namespaces=mtls_allowed_namespaces,
    )
    # Serves a strict default-src 'none' CSP on API responses and a docs-only
    # relaxed policy on /docs and /redoc when APP_ENV=dev, so Swagger UI works
    # without loosening anything in production.
    app.add_middleware(
        _middleware(SecurityHeadersMiddleware), environment=runtime.app_env
    )

    app.add_middleware(
        _middleware(CORSMiddleware),
        allow_origins=list(runtime.allowed_origins),
        allow_credentials=True,
        allow_methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
        allow_headers=['*'],
        expose_headers=[
            'X-Content-Type-Options',
            'X-XSS-Protection',
            'X-Frame-Options',
            'Referrer-Policy',
            'Content-Security-Policy',
            'Pragma',
            'Expires',
            'Strict-Transport-Security',
            'Cache-Control',
        ],
    )

    # Instrumenting last makes the OTel ASGI middleware the outermost layer, so
    # the SERVER span wraps CORS, security headers and auth rather than starting
    # after them. This is the sole source of HTTP spans and metrics for this app.
    instrument_fastapi(app)
