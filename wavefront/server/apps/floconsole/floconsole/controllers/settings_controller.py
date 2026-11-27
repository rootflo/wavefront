from authz_module import Legacy, requires
from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from floconsole.di.application_container import ApplicationContainer
from floconsole.services.extension_settings import parse_extensions

settings_router = APIRouter(prefix='/v1/settings')


@settings_router.get(
    '/extensions',
    dependencies=[
        Depends(requires('console:ListExtensions', legacy=Legacy.CONSOLE_USER))
    ],
)
@inject
async def list_extensions(
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    config: dict = Depends(Provide[ApplicationContainer.config]),
):
    """The remote UI extensions the console should load; none by default."""
    remotes = parse_extensions((config.get('extensions') or {}).get('remotes'))
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'extensions': remotes}),
    )
