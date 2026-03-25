import base64

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from inference_app.inference_app_container import InferenceAppContainer
from inference_app.service.image_embedding import ImageEmbedding
from pydantic import BaseModel


class ImagePayload(BaseModel):
    image_data: str


inference_app_router = APIRouter()


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
