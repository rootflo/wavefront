"""Every floware route, for ``authz lint-routes`` / ``authz export-catalog``.

Builds an app with the same routes the server serves, including the ones it
adds conditionally (guardrails) or at startup (API services management), but
with no middleware and no lifespan, so nothing connects anywhere.
"""

from fastapi import FastAPI

from floware.router.setup import FLOWARE_PREFIX, FLOWARE_ROUTERS


class _NoServices:
    def get_all_services(self) -> dict:
        return {}


def build_app() -> FastAPI:
    from api_services_module.core.router import ProxyRouter
    from guardrails_module.controllers.guardrails_controller import (
        guardrails_router,
    )

    app = FastAPI()
    for router in [*FLOWARE_ROUTERS, guardrails_router]:
        app.include_router(router, prefix=FLOWARE_PREFIX)
    # Static management routes only: proxied API routes are created per
    # service at runtime and all declare api_services:InvokeApi.
    api_services = ProxyRouter(
        proxy=None, service_registry=_NoServices(), response_formatter=None
    )
    app.include_router(api_services.router, prefix=FLOWARE_PREFIX)
    return app
