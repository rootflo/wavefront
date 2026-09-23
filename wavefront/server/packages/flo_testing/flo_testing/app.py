"""Building the FastAPI app under test.

Every module mounted the same two middlewares in the same order, except
inference_module which silently omitted RequestIdMiddleware. Going through one
builder keeps the app under test the same shape as the real one.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient


def build_app(*routers: Any, prefix: str = '/floware') -> FastAPI:
    from common_module.middleware.request_id_middleware import RequestIdMiddleware
    from user_management_module.authorization.require_auth import (
        RequireAuthMiddleware,
    )

    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(RequireAuthMiddleware)
    for router in routers:
        app.include_router(router, prefix=prefix)
    return app


def make_test_client(*routers: Any, prefix: str = '/floware') -> TestClient:
    """A TestClient over the given routers with the standard middleware stack."""
    return TestClient(build_app(*routers, prefix=prefix))
