import base64
import re

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
    ImageSegmentRequest,
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
    else:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Image must be a data URL (data:image/<type>;base64,<data>)'
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


@image_controller.post('/segment')
@inject
async def segment_image(
    request: ImageSegmentRequest,
    image_service: ImageService = Depends(Provide[GoldContainer.image_service]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """
    Sync SAM segmentation for Fraud Search: returns per-item crop previews
    so the UI can ask which segment to search with.
    """
    image_str = request.image
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
    else:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Image must be a data URL (data:image/<type>;base64,<data>)'
            ),
        )
    if not gold_image:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse('Empty image file'),
        )
    try:
        result = await image_service.segment_image(
            gold_image, segment_prompt=request.segment_prompt or 'jewellery'
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response_formatter.buildErrorResponse(str(e)),
        )
    except Exception as e:
        logger.error(f'Error segmenting image: {e}', exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=response_formatter.buildErrorResponse(
                'Failed to segment image'
            ),
        )
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
    else:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                 'Image must be a data URL (data:image/<type>;base64,<data>)'
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
