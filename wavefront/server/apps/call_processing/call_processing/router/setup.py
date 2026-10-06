from fastapi import FastAPI

from call_processing.controllers.cache_controller import cache_router
from call_processing.controllers.health_controller import health_router
from call_processing.controllers.webhook_controller import webhook_router

CALL_PROCESSING_ROUTERS = [
    (health_router, ''),
    (webhook_router, '/webhooks'),
    (cache_router, '/api'),
]


def include_routers(app: FastAPI) -> None:
    for router, prefix in CALL_PROCESSING_ROUTERS:
        app.include_router(router, prefix=prefix)
