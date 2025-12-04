from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from dependency_injector.wiring import inject, Provide

from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from common_module.common_container import CommonContainer
from agents_module.agents_container import AgentsContainer
from agents_module.services.namespace_service import NamespaceService

namespace_router = APIRouter()


@namespace_router.get('/v1/namespaces')
@inject
async def list_namespaces(
    namespace_service: NamespaceService = Depends(
        Provide[AgentsContainer.namespace_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    List all namespaces

    Returns:
        JSONResponse: List of all namespaces
    """
    logger.info('Listing all namespaces')

    namespaces = await namespace_service.list_namespaces()

    logger.info(f'Successfully retrieved {len(namespaces)} namespaces')
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Namespaces retrieved successfully',
                'data': {'namespaces': namespaces, 'count': len(namespaces)},
            }
        ),
    )
