from uuid import UUID

from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from user_management_module.utils.user_utils import check_is_admin

from chatbots_module.chatbots_container import ChatbotsContainer
from chatbots_module.models.chatbot_schemas import (
    CreateChatbotPayload,
    UpdateChatbotPayload,
)
from chatbots_module.services.chatbot_service import (
    ChatbotNotFoundError,
    ChatbotService,
    ChatbotValidationError,
)

chatbot_router = APIRouter()

# Every route here is admin-gated, reads included. A chatbot's system_prompt is
# authored content -- it can carry proprietary instructions or embedded
# reference data -- and it is pinned into every session opened against the
# chatbot, so an unprivileged edit would change the premise of other people's
# conversations.
NON_ADMIN_ERROR = 'Only admins can manage chatbots'


@chatbot_router.post('/v1/chatbots')
@inject
async def create_chatbot(
    request: Request,
    payload: CreateChatbotPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    chatbot_service: ChatbotService = Depends(
        Provide[ChatbotsContainer.chatbot_service]
    ),
):
    """Create a chatbot. Starts disabled unless `enabled` is passed."""
    role_id = request.state.session.role_id

    is_admin = await check_is_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(NON_ADMIN_ERROR),
        )

    try:
        chatbot = await chatbot_service.create_chatbot(
            name=payload.name,
            namespace=payload.namespace,
            description=payload.description,
            system_prompt=payload.system_prompt,
            welcome_message=payload.welcome_message,
            llm_config_id=payload.llm_config_id,
            config=payload.config,
            enabled=payload.enabled,
        )
    except ChatbotValidationError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Chatbot created successfully', 'chatbot': chatbot}
        ),
    )


@chatbot_router.get('/v1/chatbots')
@inject
async def list_chatbots(
    request: Request,
    namespace: str | None = Query(None, description='Filter by namespace'),
    enabled: bool | None = Query(None, description='Filter by enabled flag'),
    limit: int = Query(100, ge=1, le=500),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    chatbot_service: ChatbotService = Depends(
        Provide[ChatbotsContainer.chatbot_service]
    ),
):
    """List chatbots, including their system prompts. Admin only."""
    role_id = request.state.session.role_id

    is_admin = await check_is_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(NON_ADMIN_ERROR),
        )

    chatbots = await chatbot_service.list_chatbots(
        namespace=namespace, enabled=enabled, limit=limit
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'chatbots': chatbots}),
    )


@chatbot_router.get('/v1/chatbots/{chatbot_id}')
@inject
async def get_chatbot(
    request: Request,
    chatbot_id: UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    chatbot_service: ChatbotService = Depends(
        Provide[ChatbotsContainer.chatbot_service]
    ),
):
    """Read one chatbot, including its system prompt. Admin only."""
    role_id = request.state.session.role_id

    is_admin = await check_is_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(NON_ADMIN_ERROR),
        )

    try:
        chatbot = await chatbot_service.get_chatbot(chatbot_id)
    except ChatbotNotFoundError as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'chatbot': chatbot.to_dict()}),
    )


@chatbot_router.patch('/v1/chatbots/{chatbot_id}')
@inject
async def update_chatbot(
    request: Request,
    chatbot_id: UUID,
    payload: UpdateChatbotPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    chatbot_service: ChatbotService = Depends(
        Provide[ChatbotsContainer.chatbot_service]
    ),
):
    """Partial update.

    Editing `system_prompt` affects new sessions only -- existing ones keep the
    snapshot taken when they were opened.
    """
    role_id = request.state.session.role_id

    is_admin = await check_is_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(NON_ADMIN_ERROR),
        )

    try:
        chatbot = await chatbot_service.update_chatbot(
            chatbot_id,
            name=payload.name,
            description=payload.description,
            system_prompt=payload.system_prompt,
            welcome_message=payload.welcome_message,
            llm_config_id=payload.llm_config_id,
            config=payload.config,
            enabled=payload.enabled,
        )
    except ChatbotNotFoundError as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    except ChatbotValidationError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Chatbot updated successfully', 'chatbot': chatbot}
        ),
    )


@chatbot_router.delete('/v1/chatbots/{chatbot_id}')
@inject
async def delete_chatbot(
    request: Request,
    chatbot_id: UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    chatbot_service: ChatbotService = Depends(
        Provide[ChatbotsContainer.chatbot_service]
    ),
):
    """Soft delete. Existing sessions stay readable but accept no new messages."""
    role_id = request.state.session.role_id

    is_admin = await check_is_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(NON_ADMIN_ERROR),
        )

    try:
        await chatbot_service.delete_chatbot(chatbot_id)
    except ChatbotNotFoundError as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    logger.info(f'Chatbot soft-deleted: {chatbot_id}')
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Chatbot deleted successfully'}
        ),
    )
