import base64
import re
import httpx

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from common_module.log.logger import logger
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import APIRouter
from fastapi import Depends
from fastapi import status
from fastapi.responses import JSONResponse
from gold_module.gold_container import GoldContainer
from gold_module.services.image_service import ImageService
from gold_module.models.gold_image_request import (
    ImageAnalysisRequest,
    AdhocImageUploadRequest,
)

image_controller = APIRouter()


@image_controller.post('/analyse')
@inject
async def process_image(
    request: ImageAnalysisRequest,
    image_service: ImageService = Depends(Provide[GoldContainer.image_service]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    image_str = request.image
    metadata = request.metadata
    extra_fields = metadata.get_extra_fields()
    if extra_fields:
        logger.info(f'Unnecessary extra fields: {extra_fields}')

    # remove extra not required fields from metadata
    filtered_metadata_dict = metadata.get_defined_fields()

    gold_image = None

    # Check for data URL (base64 with MIME)
    data_url_pattern = r'^data:(image/\w+);base64,(.+)'
    match = re.match(data_url_pattern, image_str)
    if match:
        try:
            gold_image = base64.b64decode(match.group(2))
        except Exception:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'Invalid base64 image encoding'
                ),
            )
    elif image_str.startswith('http://') or image_str.startswith('https://'):
        # Download the image from the URL
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(image_str)
                if resp.status_code != 200:
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content=response_formatter.buildErrorResponse(
                            'Failed to download image from URL'
                        ),
                    )
                gold_image = resp.content
        except Exception:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'Error downloading image from URL'
                ),
            )
    else:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Image must be a data URL or a direct image URL'
            ),
        )
    if not gold_image:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse('Empty image file'),
        )
    result = await image_service.process_image(gold_image, filtered_metadata_dict)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(result),
    )


@image_controller.post('/historical_images')
@inject
async def upload_historical_images(
    request: AdhocImageUploadRequest,
    image_service: ImageService = Depends(Provide[GoldContainer.image_service]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    image_str = request.image
    image_name = request.loan_id

    gold_image = None
    # Check for data URL (base64 with MIME)
    data_url_pattern = r'^data:(image/\w+);base64,(.+)'
    match = re.match(data_url_pattern, image_str)
    if match:
        try:
            gold_image = base64.b64decode(match.group(2))
        except Exception:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'Invalid base64 image encoding'
                ),
            )
    elif image_str.startswith('http://') or image_str.startswith('https://'):
        # Download the image from the URL
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(image_str)
                if resp.status_code != 200:
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content=response_formatter.buildErrorResponse(
                            'Failed to download image from URL'
                        ),
                    )
                gold_image = resp.content
        except Exception:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'Error downloading image from URL'
                ),
            )
    else:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Image must be a data URL or a direct image URL'
            ),
        )
    if not gold_image:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse('Empty image file'),
        )
    result = await image_service.save_image(gold_image, image_name)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(result),
    )
