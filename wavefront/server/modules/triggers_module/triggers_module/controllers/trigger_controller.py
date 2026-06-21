from json import JSONDecodeError
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID

from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from triggers_module.models.trigger_schemas import CreateTriggerRequest
from triggers_module.services.trigger_crud_service import (
    EntityNotFound,
    InvalidTriggerState,
    TriggerCrudService,
    TriggerNotFound,
)
from triggers_module.services.trigger_push_receiver import (
    TriggerMismatch,
    TriggerPushReceiver,
)
from triggers_module.triggers_container import TriggersContainer


trigger_router = APIRouter(prefix='/v1/triggers', tags=['triggers'])


def _is_safe_redirect(url: str) -> bool:
    parsed = urlparse(url)
    # Allow only relative URLs (no scheme, no host) to prevent open redirects.
    return not parsed.scheme and not parsed.netloc


@trigger_router.post('', status_code=status.HTTP_201_CREATED)
@inject
async def create_trigger(
    payload: CreateTriggerRequest,
    trigger_crud_service: TriggerCrudService = Depends(
        Provide[TriggersContainer.trigger_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    try:
        result = await trigger_crud_service.create_trigger(payload)
    except EntityNotFound as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    except InvalidTriggerState as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Trigger created',
                'data': result.model_dump(mode='json'),
            }
        ),
    )


@trigger_router.get('/oauth/google/callback')
@inject
async def gmail_oauth_callback(
    state: str = Query(...),
    code: str = Query(...),
    success_redirect_url: Optional[str] = Query(default=None),
    failure_redirect_url: Optional[str] = Query(default=None),
    trigger_crud_service: TriggerCrudService = Depends(
        Provide[TriggersContainer.trigger_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    try:
        result = await trigger_crud_service.complete_oauth(state=state, code=code)
    except TriggerNotFound as exc:
        if failure_redirect_url and _is_safe_redirect(failure_redirect_url):
            return RedirectResponse(url=failure_redirect_url)
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    except InvalidTriggerState as exc:
        if failure_redirect_url and _is_safe_redirect(failure_redirect_url):
            return RedirectResponse(url=failure_redirect_url)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    if success_redirect_url and _is_safe_redirect(success_redirect_url):
        return RedirectResponse(url=success_redirect_url)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Trigger activated',
                'data': result.model_dump(mode='json'),
            }
        ),
    )


@trigger_router.get('')
@inject
async def list_triggers(
    provider: Optional[str] = Query(default=None),
    namespace: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias='status'),
    limit: int = Query(default=100, ge=1, le=500),
    trigger_crud_service: TriggerCrudService = Depends(
        Provide[TriggersContainer.trigger_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    triggers = await trigger_crud_service.list_triggers(
        provider=provider, namespace=namespace, status=status_filter, limit=limit
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'data': [t.model_dump(mode='json') for t in triggers]}
        ),
    )


@trigger_router.get('/{trigger_id}')
@inject
async def get_trigger(
    trigger_id: UUID,
    trigger_crud_service: TriggerCrudService = Depends(
        Provide[TriggersContainer.trigger_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    try:
        result = await trigger_crud_service.get_trigger(trigger_id)
    except TriggerNotFound as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'data': result.model_dump(mode='json')}
        ),
    )


@trigger_router.post('/{trigger_id}/pause')
@inject
async def pause_trigger(
    trigger_id: UUID,
    trigger_crud_service: TriggerCrudService = Depends(
        Provide[TriggersContainer.trigger_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    try:
        result = await trigger_crud_service.pause_trigger(trigger_id)
    except TriggerNotFound as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'data': result.model_dump(mode='json')}
        ),
    )


@trigger_router.post('/{trigger_id}/resume')
@inject
async def resume_trigger(
    trigger_id: UUID,
    trigger_crud_service: TriggerCrudService = Depends(
        Provide[TriggersContainer.trigger_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    try:
        result = await trigger_crud_service.resume_trigger(trigger_id)
    except TriggerNotFound as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'data': result.model_dump(mode='json')}
        ),
    )


@trigger_router.post('/{trigger_id}/retry')
@inject
async def retry_trigger(
    trigger_id: UUID,
    trigger_crud_service: TriggerCrudService = Depends(
        Provide[TriggersContainer.trigger_crud_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    try:
        result = await trigger_crud_service.retry_trigger(trigger_id)
    except TriggerNotFound as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    except InvalidTriggerState as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'data': result.model_dump(mode='json')}
        ),
    )


@trigger_router.delete('/{trigger_id}', status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_trigger(
    trigger_id: UUID,
    trigger_crud_service: TriggerCrudService = Depends(
        Provide[TriggersContainer.trigger_crud_service]
    ),
):
    try:
        await trigger_crud_service.delete_trigger(trigger_id)
    except TriggerNotFound:
        pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@trigger_router.post('/{trigger_id}/{agentic_id}/invoke')
@inject
async def invoke_trigger(
    request: Request,
    trigger_id: UUID,
    agentic_id: UUID,
    authorization: Optional[str] = Header(default=None),
    push_receiver: TriggerPushReceiver = Depends(
        Provide[TriggersContainer.trigger_push_receiver]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    try:
        raw_payload = await request.json()
    except (JSONDecodeError, ValueError) as exc:
        logger.warning(f'Trigger invoke received invalid JSON for {trigger_id}: {exc}')
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse('invalid_json_payload'),
        )

    try:
        result = await push_receiver.handle_push(
            trigger_id=trigger_id,
            agentic_id=agentic_id,
            raw_payload=raw_payload,
            authorization_header=authorization,
        )
    except TriggerMismatch as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    except Exception as exc:
        logger.exception(f'Trigger invoke failed for {trigger_id}: {exc}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse('internal_error'),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(result),
    )
