"""Every call processing route, for ``authz lint-routes`` / ``authz export-catalog``."""

from fastapi import FastAPI

from call_processing.router.setup import include_routers


def build_app() -> FastAPI:
    app = FastAPI()
    include_routers(app)
    return app
