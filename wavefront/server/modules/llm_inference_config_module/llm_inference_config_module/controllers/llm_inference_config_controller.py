import uuid

from auth_module.auth_container import AuthContainer
from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from db_repo_module.models.role import Role
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from llm_inference_config_module.container import LlmInferenceConfigContainer
from llm_inference_config_module.models.schemas import (
    CreateLlmInferenceConfigPayload,
    UpdateLlmInferenceConfigPayload,
    InferenceEngineType,
    UNSET,
)
from llm_inference_config_module.services.llm_inference_config_service import (
    LlmInferenceConfigService,
)
from user_management_module.constants.auth import SERVICE_AUTH_ROLE_ID

llm_inference_config_router = APIRouter()


@inject
async def check_admin(
    role_id: str,
    role_repository: SQLAlchemyRepository[Role] = Depends(
        Provide[AuthContainer.role_repository]
    ),
) -> bool:
    if role_id == SERVICE_AUTH_ROLE_ID:
        return True
    role = await role_repository.find_one(id=role_id)
    if not role:
        return False
    return role.name == 'admin'


@llm_inference_config_router.post('/v1/llm-inference-configs')
@inject
async def create_llm_inference_config(
    request: Request,
    payload: CreateLlmInferenceConfigPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    llm_inference_config_service: LlmInferenceConfigService = Depends(
        Provide[LlmInferenceConfigContainer.llm_inference_config_service]
    ),
):
    role_id = request.state.session.role_id
    is_admin = await check_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Admin access required to manage LLM inference configurations'
            ),
        )

    try:
        config_dict = await llm_inference_config_service.create_config(
            llm_model=payload.llm_model,
            display_name=payload.display_name,
            api_key=payload.api_key,
            type=payload.type.value,
            base_url=payload.base_url,
            parameters=payload.parameters,
            model_type=payload.model_type,
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response_formatter.buildSuccessResponse(
                {
                    'message': 'LLM inference configuration created successfully',
                    'config': config_dict,
                }
            ),
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(str(e)),
        )


@llm_inference_config_router.get('/v1/llm-inference-configs')
@inject
async def get_llm_inference_configs(
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    llm_inference_config_service: LlmInferenceConfigService = Depends(
        Provide[LlmInferenceConfigContainer.llm_inference_config_service]
    ),
):
    role_id = request.state.session.role_id
    is_admin = await check_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Admin access required to manage LLM inference configurations'
            ),
        )

    try:
        configs_list = await llm_inference_config_service.list_configs()

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse({'configs': configs_list}),
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(str(e)),
        )


@llm_inference_config_router.get('/v1/llm-inference-configs/{config_id}')
@inject
async def get_llm_inference_config(
    request: Request,
    config_id: uuid.UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    llm_inference_config_service: LlmInferenceConfigService = Depends(
        Provide[LlmInferenceConfigContainer.llm_inference_config_service]
    ),
):
    try:
        config_dict = await llm_inference_config_service.get_config(config_id)
        if not config_dict:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=response_formatter.buildErrorResponse(
                    f'LLM inference configuration not found: {config_id}'
                ),
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(config_dict),
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(str(e)),
        )


@llm_inference_config_router.patch('/v1/llm-inference-configs/{config_id}')
@inject
async def update_llm_inference_config(
    request: Request,
    config_id: uuid.UUID,
    payload: UpdateLlmInferenceConfigPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    llm_inference_config_service: LlmInferenceConfigService = Depends(
        Provide[LlmInferenceConfigContainer.llm_inference_config_service]
    ),
):
    role_id = request.state.session.role_id
    is_admin = await check_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Admin access required to manage LLM inference configurations'
            ),
        )

    try:
        # Validate payload fields before update
        update_data = {}
        if payload.llm_model is not UNSET:
            update_data['llm_model'] = payload.llm_model
        if payload.display_name is not UNSET:
            if payload.display_name is None or (
                isinstance(payload.display_name, str)
                and not payload.display_name.strip()
            ):
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=response_formatter.buildErrorResponse(
                        'display_name cannot be null or empty'
                    ),
                )
            update_data['display_name'] = payload.display_name
        if payload.api_key is not UNSET:
            update_data['api_key'] = payload.api_key
        if payload.type is not UNSET:
            if payload.type is None:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=response_formatter.buildErrorResponse(
                        'type cannot be null or empty'
                    ),
                )
            if hasattr(payload.type, 'value'):
                # It's an enum object
                update_data['type'] = payload.type.value
            elif isinstance(payload.type, str) and payload.type in [
                e.value for e in InferenceEngineType
            ]:
                # It's a valid enum value string
                update_data['type'] = payload.type
            else:
                # Invalid value
                valid_values = [e.value for e in InferenceEngineType]
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=response_formatter.buildErrorResponse(
                        f'Invalid type value. Must be one of: {valid_values}'
                    ),
                )
        if payload.model_type is not UNSET:
            if payload.model_type is None:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=response_formatter.buildErrorResponse(
                        'model_type cannot be null'
                    ),
                )
            if payload.model_type not in ['llm', 'embedding']:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=response_formatter.buildErrorResponse(
                        'Invalid model_type value. Must be "llm" or "embedding"'
                    ),
                )
            update_data['model_type'] = payload.model_type
        if payload.base_url is not UNSET:
            update_data['base_url'] = payload.base_url
        if payload.parameters is not UNSET:
            update_data['parameters'] = payload.parameters

        if not update_data:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'No valid fields provided for update'
                ),
            )

        # Update via service (handles caching)
        config_dict = await llm_inference_config_service.update_config(
            config_id, **update_data
        )

        if not config_dict:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=response_formatter.buildErrorResponse(
                    f'LLM inference configuration not found: {config_id}'
                ),
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {
                    'message': 'LLM inference configuration updated successfully',
                    'config': config_dict,
                }
            ),
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(str(e)),
        )


@llm_inference_config_router.delete('/v1/llm-inference-configs/{config_id}')
@inject
async def delete_llm_inference_config(
    request: Request,
    config_id: uuid.UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    llm_inference_config_service: LlmInferenceConfigService = Depends(
        Provide[LlmInferenceConfigContainer.llm_inference_config_service]
    ),
):
    role_id = request.state.session.role_id
    is_admin = await check_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Admin access required to manage LLM inference configurations'
            ),
        )

    try:
        deleted = await llm_inference_config_service.delete_config(config_id)
        if not deleted:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=response_formatter.buildErrorResponse(
                    f'LLM inference configuration not found: {config_id}'
                ),
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {
                    'message': 'LLM inference configuration deleted successfully',
                    'config_id': str(config_id),
                }
            ),
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(str(e)),
        )
