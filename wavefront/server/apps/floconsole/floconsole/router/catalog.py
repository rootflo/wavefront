"""Every console route, for ``authz lint-routes`` / ``authz export-catalog``."""

from fastapi import FastAPI

from floconsole.router.setup import include_routers


def build_app() -> FastAPI:
    app = FastAPI()
    include_routers(app)
    return app
