from fastapi import FastAPI

from inference_app.controllers.health_controller import health_router
from inference_app.controllers.inference_controller import inference_app_router

INFERENCE_PREFIX = '/inference'

INFERENCE_ROUTERS = [
    health_router,
    inference_app_router,
]


def include_routers(app: FastAPI) -> None:
    for router in INFERENCE_ROUTERS:
        app.include_router(router, prefix=INFERENCE_PREFIX)
