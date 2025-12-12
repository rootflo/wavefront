import base64
from typing import Any, Dict

from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from inference_app.inference_app_container import InferenceAppContainer
from inference_app.service.image_analyser import ImageClarityService
from inference_app.service.model_inference import (
    ModelInferenceService,
    PreprocessingStep,
)
from inference_app.service.model_repository import ModelRepository
from inference_app.service.image_embedding import ImageEmbedding
from pydantic import BaseModel, Field


class InferencePayload(BaseModel):
    data: str
    payload_type: str
    model_info: dict
    preprocessing_steps: list[PreprocessingStep]
    max_expected_variance: int = Field(default=1000)
    resize_width: int = Field(default=224)
    resize_height: int = Field(default=224)
    gaussian_blur_kernel: int = Field(default=3)
    min_threshold: int = Field(default=50)
    max_threshold: int = Field(default=150)
    normalize_mean: str = Field(default='0.485,0.456,0.406')
    normalize_std: str = Field(default='0.229,0.224,0.225')


class InferenceResult(BaseModel):
    results: Dict[str, Any] = Field(..., description='Dictionary of inference results')


class ImagePayload(BaseModel):
    image_data: str


inference_app_router = APIRouter()


@inference_app_router.post('/v1/model-repository/model/{model_id}/infer')
@inject
async def generic_inference_handler(
    payload: InferencePayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    model_repository: ModelRepository = Depends(
        Provide[InferenceAppContainer.model_repository]
    ),
    image_analyser: ImageClarityService = Depends(
        Provide[InferenceAppContainer.image_analyser]
    ),
    config: dict = Depends(Provide[InferenceAppContainer.config]),
    model_inference: ModelInferenceService = Depends(
        Provide[InferenceAppContainer.model_inference]
    ),
):
    try:
        provider = config['cloud_config']['cloud_provider']
        model_storage_bucket = (
            config['gcp']['model_storage_bucket']
            if provider.lower() == 'gcp'
            else config['aws']['model_storage_bucket']
        )

        logger.info(
            f'Loading model from bucket: {model_storage_bucket}, model_info: {payload.model_info}'
        )
        model = await model_repository.load_model(
            model_info=payload.model_info, bucket_name=model_storage_bucket
        )
        logger.debug('Model loaded successfully for model_id')

        if payload.payload_type.lower() == 'image':
            base64_data_uri = payload.data
            parts = base64_data_uri.split(',')
            if len(parts) == 2:
                base64_data = parts[1]
                image_bytes = base64.b64decode(base64_data)

                clarity_score = image_analyser.laplacian_detection(
                    image_bytes, payload.max_expected_variance
                )

                infer_data = model_inference.model_infer_score(
                    model,
                    image_bytes,
                    payload.resize_width,
                    payload.resize_height,
                    payload.normalize_mean,
                    payload.normalize_std,
                    payload.gaussian_blur_kernel,
                    payload.min_threshold,
                    payload.max_threshold,
                    preprocessing_steps=payload.preprocessing_steps,
                )
                logger.debug('Model inference completed successfully for model_id')

                inference_results = InferenceResult(
                    results={
                        'clarity_score': clarity_score,
                        'infer_data': infer_data,
                        'data_type': payload.payload_type.lower(),
                    }
                )

                logger.info('Inference request completed successfully for model_id')
                return JSONResponse(
                    status_code=status.HTTP_201_CREATED,
                    content=response_formatter.buildSuccessResponse(
                        inference_results.dict()
                    ),
                )
            else:
                error_msg = (
                    "Input data is not in expected Data URI format (missing 'base64,')."
                )
                logger.error(
                    f"Expected Data URI format with 'base64,' prefix. "
                    f'Data length: {len(base64_data_uri)}'
                )
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=response_formatter.buildErrorResponse(error_msg),
                )
        else:
            error_msg = f"Invalid payload_type: {payload.payload_type}. Accepted values are 'image'"
            logger.error(f'{error_msg}')
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'Invalid payload_type. Accepted values are "image"'
                ),
            )
    except Exception as e:
        logger.error(f'Error in generic_inference_handler {str(e)}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse('Internal server error'),
        )


@inference_app_router.post('/v1/query/embeddings')
@inject
async def image_embedding(
    payload: ImagePayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    image_embedding_service: ImageEmbedding = Depends(
        Provide[InferenceAppContainer.image_embedding]
    ),
):
    # 1. Decode Base64 string
    base64_data_uri = payload.image_data
    parts = base64_data_uri.split(',')
    base64_data = parts[1] if len(parts) == 2 else parts[0]
    image_data = base64.b64decode(base64_data)
    embeddings = image_embedding_service.query_embed(image_data)
    if not embeddings:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'No Embedding data is present'
            ),
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(data={'response': embeddings}),
    )
