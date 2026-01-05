from fastapi import APIRouter
from fastapi import Depends
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide

from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from common_module.common_container import CommonContainer
from floconsole.di.application_container import ApplicationContainer
from floconsole.services.floware_proxy_service import FlowareProxyService

floware_proxy_router = APIRouter(prefix='/v1')


@floware_proxy_router.get('/{app_id}/floware/{path:path}')
@inject
async def proxy_get_request(
    app_id: str,
    path: str,
    request: Request,
    floware_proxy_service: FlowareProxyService = Depends(
        Provide[ApplicationContainer.floware_proxy_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """Proxy GET requests to floware service"""
    try:
        result = await floware_proxy_service.proxy_request(
            method='GET', app_id=app_id, path=path, request=request
        )
        logger.info(f'GET proxy request successful for app {app_id} path {path}')
        return result
    except Exception as e:
        logger.error(f'GET proxy request failed for app {app_id} path {path}: {str(e)}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Proxy request failed: {str(e)}'
            ),
        )


@floware_proxy_router.post('/{app_id}/floware/{path:path}')
@inject
async def proxy_post_request(
    app_id: str,
    path: str,
    request: Request,
    floware_proxy_service: FlowareProxyService = Depends(
        Provide[ApplicationContainer.floware_proxy_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """Proxy POST requests to floware service"""
    try:
        result = await floware_proxy_service.proxy_request(
            method='POST', app_id=app_id, path=path, request=request
        )
        logger.info(f'POST proxy request successful for app {app_id} path {path}')
        return result
    except Exception as e:
        logger.error(
            f'POST proxy request failed for app {app_id} path {path}: {str(e)}'
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Proxy request failed: {str(e)}'
            ),
        )


@floware_proxy_router.put('/{app_id}/floware/{path:path}')
@inject
async def proxy_put_request(
    app_id: str,
    path: str,
    request: Request,
    floware_proxy_service: FlowareProxyService = Depends(
        Provide[ApplicationContainer.floware_proxy_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """Proxy PUT requests to floware service"""
    try:
        result = await floware_proxy_service.proxy_request(
            method='PUT', app_id=app_id, path=path, request=request
        )
        logger.info(f'PUT proxy request successful for app {app_id} path {path}')
        return result
    except Exception as e:
        logger.error(f'PUT proxy request failed for app {app_id} path {path}: {str(e)}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Proxy request failed: {str(e)}'
            ),
        )


@floware_proxy_router.patch('/{app_id}/floware/{path:path}')
@inject
async def proxy_patch_request(
    app_id: str,
    path: str,
    request: Request,
    floware_proxy_service: FlowareProxyService = Depends(
        Provide[ApplicationContainer.floware_proxy_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """Proxy PATCH requests to floware service"""
    try:
        result = await floware_proxy_service.proxy_request(
            method='PATCH', app_id=app_id, path=path, request=request
        )
        logger.info(f'PATCH proxy request successful for app {app_id} path {path}')
        return result
    except Exception as e:
        logger.error(
            f'PATCH proxy request failed for app {app_id} path {path}: {str(e)}'
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Proxy request failed: {str(e)}'
            ),
        )


@floware_proxy_router.delete('/{app_id}/floware/{path:path}')
@inject
async def proxy_delete_request(
    app_id: str,
    path: str,
    request: Request,
    floware_proxy_service: FlowareProxyService = Depends(
        Provide[ApplicationContainer.floware_proxy_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """Proxy DELETE requests to floware service"""
    try:
        result = await floware_proxy_service.proxy_request(
            method='DELETE', app_id=app_id, path=path, request=request
        )
        logger.info(f'DELETE proxy request successful for app {app_id} path {path}')
        return result
    except Exception as e:
        logger.error(
            f'DELETE proxy request failed for app {app_id} path {path}: {str(e)}'
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Proxy request failed: {str(e)}'
            ),
        )
