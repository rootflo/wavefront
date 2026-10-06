from fastapi import FastAPI

from floconsole.controllers.app_controller import app_router
from floconsole.controllers.app_user_controller import app_user_router
from floconsole.controllers.auth_controller import auth_router
from floconsole.controllers.floware_proxy_controller import floware_proxy_router
from floconsole.controllers.user_controller import user_router

FLOCONSOLE_PREFIX = '/floconsole'

FLOCONSOLE_ROUTERS = [
    auth_router,
    floware_proxy_router,
    user_router,
    app_router,
    app_user_router,
]


def include_routers(app: FastAPI) -> None:
    for router in FLOCONSOLE_ROUTERS:
        app.include_router(router, prefix=FLOCONSOLE_PREFIX)
