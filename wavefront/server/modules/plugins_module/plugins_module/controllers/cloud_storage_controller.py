from dependency_injector.wiring import inject, Provide
from fastapi import Depends, Query, status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from flo_cloud.cloud_storage import CloudStorageManager
from plugins_module.plugins_container import PluginsContainer


cloud_storage_router = APIRouter()


@cloud_storage_router.get('/v1/storage/signed-url')
@inject
async def get_resource_presigned_url(
    resource_url: str = Query(..., description='The cloud storage URL of the resource'),
    expires_in: int = Query(
        300, description='Expiry time in seconds for the presigned URL'
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    cloud_manager: CloudStorageManager = Depends(
        Provide[PluginsContainer.cloud_manager]
    ),
):
    try:
        bucket_name, key = cloud_manager.get_bucket_key(resource_url)
        presigned_url = cloud_manager.generate_presigned_url(
            bucket_name=bucket_name,
            key=key,
            type='GET',
            expiresIn=expires_in,
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'resource_url': presigned_url}
            ),
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )
