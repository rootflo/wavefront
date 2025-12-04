from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from fastapi import status

from common_module.response_formatter import ResponseFormatter

from common_module.common_container import CommonContainer
from dependency_injector.wiring import inject, Provide

from image_search_module.image_search_container import ImageSearchContainer
from image_search_module.services.ikb_service import IKBService
from image_search_module.models.ikb_models import (
    CreateIKBRequest,
    IKBInfo,
    IKBType,
    IKBImageAddRequest,
    IKBSearchRequest,
    IKBSearchResponse,
)

image_search_router = APIRouter(prefix='/ikb')


# IKB Management Endpoints
@image_search_router.post('/create', response_model=IKBInfo)
@inject
async def create_ikb(
    payload: CreateIKBRequest,
    ikb_service: IKBService = Depends(Provide[ImageSearchContainer.ikb_service]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """Create a new Image Knowledge Base"""

    ikb_info = await ikb_service.create_ikb(payload)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            ikb_info.model_dump(mode='json')
        ),
    )


@image_search_router.get('/', response_model=List[IKBInfo])
@inject
async def list_ikbs(
    ikb_type: Optional[IKBType] = Query(None, description='Filter by IKB type'),
    ikb_service: IKBService = Depends(Provide[ImageSearchContainer.ikb_service]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """List all Image Knowledge Bases"""

    ikbs = await ikb_service.list_ikbs(ikb_type=ikb_type)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'ikbs': [ikb.model_dump(mode='json') for ikb in ikbs]}
        ),
    )


@image_search_router.get('/{ikb_id}', response_model=IKBInfo)
@inject
async def get_ikb(
    ikb_id: str,
    ikb_service: IKBService = Depends(Provide[ImageSearchContainer.ikb_service]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """Get information about a specific IKB"""
    ikb = await ikb_service.get_ikb(ikb_id)

    if not ikb:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'IKB with ID {ikb_id} not found'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(ikb.model_dump(mode='json')),
    )


# Image add and Search Endpoints
@image_search_router.post('/{ikb_id}/add')
@inject
async def add_image_to_ikb(
    ikb_id: str,
    payload: IKBImageAddRequest,
    ikb_service: IKBService = Depends(Provide[ImageSearchContainer.ikb_service]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """add an image to a specific IKB"""
    result = await ikb_service.add_image_to_ikb(ikb_id, payload)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(result),
    )


@image_search_router.post('/{ikb_id}/search', response_model=IKBSearchResponse)
@inject
async def search_in_ikb(
    ikb_id: str,
    payload: IKBSearchRequest,
    ikb_service: IKBService = Depends(Provide[ImageSearchContainer.ikb_service]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """Search for similar images within a specific IKB"""
    result = await ikb_service.search_in_ikb(ikb_id, payload)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(result.dict()),
    )


@image_search_router.delete('/{ikb_id}')
@inject
async def delete_ikb(
    ikb_id: str,
    ikb_service: IKBService = Depends(Provide[ImageSearchContainer.ikb_service]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """Delete an IKB"""

    success = await ikb_service.delete_ikb(ikb_id)

    if not success:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'IKB with ID {ikb_id} not found'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'IKB deleted successfully'}
        ),
    )
