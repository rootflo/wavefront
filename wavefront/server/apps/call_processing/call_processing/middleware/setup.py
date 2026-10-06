from collections.abc import Sequence
from typing import Any, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware import _MiddlewareFactory

from common_module.middleware.security_headers import SecurityHeadersMiddleware


def _middleware(cls: type[Any]) -> _MiddlewareFactory[Any]:
    return cast(_MiddlewareFactory[Any], cls)


def add_middlewares(app: FastAPI, allowed_origins: Sequence[str]) -> None:
    # Strict default-src 'none' CSP plus the rest of the security headers; /docs
    # and /redoc get their own relaxed policy when APP_ENV=dev.
    app.add_middleware(_middleware(SecurityHeadersMiddleware))

    app.add_middleware(
        _middleware(CORSMiddleware),
        allow_origins=list(allowed_origins),
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
