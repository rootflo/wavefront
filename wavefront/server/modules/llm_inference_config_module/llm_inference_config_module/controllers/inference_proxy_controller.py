from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import Response
from dependency_injector.wiring import Provide, inject
from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from fastapi.responses import JSONResponse
from llm_inference_config_module.container import LlmInferenceConfigContainer
from llm_inference_config_module.services.inference_proxy_service import (
    InferenceProxyService,
)


inference_proxy_router = APIRouter(prefix='/v1/llm-inference')


@inference_proxy_router.post('/{model_id}/{model_call_path:path}')
@inject
async def proxy_inference_request(
    model_id: str,
    model_call_path: str,
    request: Request,
    inference_proxy_service: InferenceProxyService = Depends(
        Provide[LlmInferenceConfigContainer.inference_proxy_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
) -> Response:
    """
    Proxy inference requests to configured model endpoints.

    This endpoint accepts requests in the format:
    /v1/llm-inference/{model_id}/{model_call_path}

    Where:
    - model_id: The ID of the model configuration in the database
    - model_call_path: The remaining path to be appended to the model's base_url

    Example:
    POST /v1/llm-inference/12345/chat/completions

    Will look up model ID 12345, get its base_url (e.g., https://api.openai.com),
    and forward the request to: https://api.openai.com/chat/completions
    """
    try:
        response = await inference_proxy_service.proxy_inference_request(
            model_id=model_id, model_call_path=model_call_path, request=request
        )
        return response

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(str(e)),
        )
