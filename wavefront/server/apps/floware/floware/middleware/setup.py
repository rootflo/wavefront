import os
from typing import Any, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware import _MiddlewareFactory

from common_module.middleware.request_id_middleware import RequestIdMiddleware
from common_module.prometheus.prometheus_middleware import PrometheusMiddleware
from user_management_module.authorization.require_auth import RequireAuthMiddleware

from .security_headers import SecurityHeadersMiddleware


def _middleware(cls: type[Any]) -> _MiddlewareFactory[Any]:
    return cast(_MiddlewareFactory[Any], cls)


def add_middlewares(app: FastAPI) -> None:
    # Order matters: last added runs first on incoming requests.
    app.add_middleware(_middleware(RequestIdMiddleware))
    app.add_middleware(_middleware(RequireAuthMiddleware))
    app.add_middleware(_middleware(PrometheusMiddleware))
    app.add_middleware(
        _middleware(SecurityHeadersMiddleware)
    )  # disable to see swaggerUI

    origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173')
    allowed_origins = origins.split(',')

    app.add_middleware(
        _middleware(CORSMiddleware),
        allow_origins=allowed_origins,
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
