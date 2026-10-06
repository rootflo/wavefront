"""Custom OpenAPI schema (Bearer JWT) for the floware FastAPI app."""

from typing import Any, Callable, cast

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

OpenApiCallable = Callable[[], dict[str, Any]]


def setup_openapi(app: FastAPI, *, floware_base_url: str) -> None:
    def custom_openapi() -> dict[str, Any]:
        """Custom OpenAPI schema with Bearer authentication"""
        if app.openapi_schema:
            return app.openapi_schema

        openapi_schema = get_openapi(
            title='Flo API',
            version='1.0.0',
            description='Floware Server - AI Middleware API',
            routes=app.routes,
            servers=[{'url': floware_base_url, 'description': 'floware server'}],
        )

        # Add Bearer authentication security scheme
        # This matches the scheme_name in BearerAuth class
        openapi_schema['components']['securitySchemes'] = {
            'BearerAuth': {
                'type': 'http',
                'scheme': 'bearer',
                'bearerFormat': 'JWT',
                'description': 'Enter your JWT token',
            }
        }

        # Apply security to all endpoints by default
        # Individual endpoints can override this with dependencies=[]
        # openapi_schema["security"] = [{"BearerAuth": []}]

        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = cast(OpenApiCallable, custom_openapi)  # type: ignore[assignment]
