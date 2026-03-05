import json
from enum import Enum
from typing import Optional

from dependency_injector.wiring import inject, Provide
from fastapi import Depends, Query, status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from flo_cloud.cloud_storage import CloudStorageManager
from plugins_module.plugins_container import PluginsContainer


cloud_storage_router = APIRouter()


class StorageFileType(str, Enum):
    json = 'json'


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
    cloud_storage_manager: CloudStorageManager = Depends(
        Provide[PluginsContainer.cloud_storage_manager]
    ),
):
    try:
        bucket_name, key = cloud_storage_manager.get_bucket_key(resource_url)
        presigned_url = cloud_storage_manager.generate_presigned_url(
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


@cloud_storage_router.get('/v1/storage/read')
@inject
async def read_storage_file(
    resource_url: str = Query(..., description='The cloud storage URL of the resource'),
    type: StorageFileType = Query(StorageFileType.json, description='File type'),
    projection: Optional[str] = Query(
        None,
        description='Comma-separated list of top-level fields to return from the parsed data',
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    cloud_storage_manager: CloudStorageManager = Depends(
        Provide[PluginsContainer.cloud_storage_manager]
    ),
):
    try:
        bucket_name, key = cloud_storage_manager.get_bucket_key(resource_url)
        file_content = cloud_storage_manager.read_file(bucket_name, key)

        if type == StorageFileType.json:
            data = json.loads(file_content)
            if projection:
                fields = {f.strip() for f in projection.split(',') if f.strip()}
                if isinstance(data, dict):
                    data = {k: v for k, v in data.items() if k in fields}
                elif isinstance(data, list):
                    data = [
                        {k: v for k, v in item.items() if k in fields}
                        if isinstance(item, dict)
                        else item
                        for item in data
                    ]

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse({'data': data}),
        )
    except (json.JSONDecodeError, ValueError) as e:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=response_formatter.buildErrorResponse(
                f'Failed to parse file as {type.value}: {str(e)}'
            ),
        )
