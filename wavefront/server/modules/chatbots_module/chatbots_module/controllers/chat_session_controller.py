import asyncio
import contextlib
import json
from datetime import datetime
from uuid import UUID

from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.middleware.request_id_middleware import get_current_request_id
from common_module.response_formatter import ResponseFormatter
from common_module.utils.guardrails import guardrail_run_scope, run_scoped_stream
from db_repo_module.models.chatbot import Chatbot
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from flo_ai.llm.guarded_llm import GuardrailBlocked

from chatbots_module.chatbots_container import ChatbotsContainer
from chatbots_module.models.chat_schemas import (
    CreateChatSessionPayload,
    SendMessagePayload,
    UpdateChatSessionPayload,
)
from chatbots_module.services.chat_inference_service import (
    ChatInferenceError,
    ChatInferenceService,
)
from chatbots_module.services.chat_session_service import (
    ChatSessionNotFoundError,
    ChatSessionService,
    UnknownChatUserError,
)
from chatbots_module.services.chatbot_service import (
    ChatbotNotFoundError,
    ChatbotService,
)
from chatbots_module.utils.auth_utils import NotAUserError, current_user_id
from chatbots_module.utils.constants import ROLE_ASSISTANT, ROLE_USER

chat_session_router = APIRouter()

# Shown to the caller when generation fails, on both the JSON and the SSE path.
#
# A single constant because the two paths must not drift, and because the
# underlying exception must never reach the client: it comes from the provider
# SDK, so it can carry the configured base_url (potentially an internal gateway
# host), deployment names, org identifiers, or an API-key prefix on an auth
# failure. Every route here is open to any authenticated user, not just admins.
# The real error goes to the logs via logger.exception.
MODEL_FAILURE_MESSAGE = (
    'The model failed to respond. Your message was saved; please retry.'
)

SSE_HEADERS = {
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Content-Type': 'text/event-stream',
    'Transfer-Encoding': 'chunked',
    'X-Accel-Buffering': 'no',  # Disable nginx buffering
}


def _not_found(response_formatter: ResponseFormatter, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=response_formatter.buildErrorResponse(message),
    )


def _session_dict(session) -> dict:
    """Session payload without the pinned prompt.

    `system_prompt_snapshot` is a copy of the chatbot's system_prompt, which is
    admin-only everywhere else. Returning it here would hand it to every session
    owner and undo that gate.
    """
    payload = session.to_dict()
    payload.pop('system_prompt_snapshot', None)
    return payload


async def _require_chattable_chatbot(
    chatbot_service: ChatbotService, chatbot_id: UUID
) -> Chatbot:
    """A disabled chatbot is treated as absent.

    Raises ChatbotNotFoundError so that disabled and deleted are reported
    identically -- whether a chatbot merely exists is not something a caller who
    cannot use it should be able to learn.
    """
    chatbot = await chatbot_service.get_chatbot(chatbot_id)
    if not chatbot.enabled:
        raise ChatbotNotFoundError(f'Chatbot not found: {chatbot_id}')
    return chatbot


@chat_session_router.post('/v1/chatbots/{chatbot_id}/sessions')
@inject
async def create_chat_session(
    request: Request,
    chatbot_id: UUID,
    payload: CreateChatSessionPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    chatbot_service: ChatbotService = Depends(
        Provide[ChatbotsContainer.chatbot_service]
    ),
    chat_session_service: ChatSessionService = Depends(
        Provide[ChatbotsContainer.chat_session_service]
    ),
):
    """Open a thread against a chatbot, pinning its current system prompt."""
    try:
        user_id = current_user_id(request)
    except NotAUserError as exc:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    try:
        chatbot = await _require_chattable_chatbot(chatbot_service, chatbot_id)
    except ChatbotNotFoundError as exc:
        return _not_found(response_formatter, str(exc))

    try:
        session = await chat_session_service.create_session(
            chatbot=chatbot, user_id=user_id, title=payload.title
        )
    except UnknownChatUserError:
        # Authenticated, but by a credential whose user lives somewhere other
        # than wavefront's `user` table -- a floconsole token, for instance.
        logger.warning(f'Chat session rejected for unknown user: {user_id}')
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Your credential is not associated with a wavefront user, so it '
                'cannot own a chat session'
            ),
        )

    messages = await chat_session_service.list_messages(session.id)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Chat session created successfully',
                'session': _session_dict(session),
                'messages': [message.to_dict() for message in messages],
            }
        ),
    )


@chat_session_router.get('/v1/chat-sessions')
@inject
async def list_chat_sessions(
    request: Request,
    chatbot_id: UUID | None = Query(None, description='Filter by chatbot'),
    cursor: datetime | None = Query(
        None, description='Return sessions created before this timestamp'
    ),
    limit: int = Query(50, ge=1, le=200),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    chat_session_service: ChatSessionService = Depends(
        Provide[ChatbotsContainer.chat_session_service]
    ),
):
    """The caller's own sessions, newest first.

    Ordered by creation time, not last activity -- replying to an old thread
    does not move it up.
    """
    try:
        user_id = current_user_id(request)
    except NotAUserError as exc:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    sessions = await chat_session_service.list_sessions(
        user_id=user_id, chatbot_id=chatbot_id, cursor=cursor, limit=limit
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'sessions': [_session_dict(session) for session in sessions]}
        ),
    )


@chat_session_router.get('/v1/chat-sessions/{session_id}')
@inject
async def get_chat_session(
    request: Request,
    session_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    chat_session_service: ChatSessionService = Depends(
        Provide[ChatbotsContainer.chat_session_service]
    ),
):
    try:
        user_id = current_user_id(request)
    except NotAUserError as exc:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    try:
        session = await chat_session_service.get_owned_session(session_id, user_id)
    except ChatSessionNotFoundError as exc:
        return _not_found(response_formatter, str(exc))

    messages = await chat_session_service.list_messages(session_id, limit=limit)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'session': _session_dict(session),
                'messages': [message.to_dict() for message in messages],
            }
        ),
    )


@chat_session_router.get('/v1/chat-sessions/{session_id}/messages')
@inject
async def list_chat_messages(
    request: Request,
    session_id: UUID,
    cursor: datetime | None = Query(
        None, description='Return messages created after this timestamp'
    ),
    limit: int = Query(50, ge=1, le=200),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    chat_session_service: ChatSessionService = Depends(
        Provide[ChatbotsContainer.chat_session_service]
    ),
):
    try:
        user_id = current_user_id(request)
    except NotAUserError as exc:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    try:
        await chat_session_service.get_owned_session(session_id, user_id)
    except ChatSessionNotFoundError as exc:
        return _not_found(response_formatter, str(exc))

    messages = await chat_session_service.list_messages(
        session_id, cursor=cursor, limit=limit
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'messages': [message.to_dict() for message in messages]}
        ),
    )


@chat_session_router.patch('/v1/chat-sessions/{session_id}')
@inject
async def rename_chat_session(
    request: Request,
    session_id: UUID,
    payload: UpdateChatSessionPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    chat_session_service: ChatSessionService = Depends(
        Provide[ChatbotsContainer.chat_session_service]
    ),
):
    try:
        user_id = current_user_id(request)
    except NotAUserError as exc:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    try:
        session = await chat_session_service.update_title(
            session_id, user_id, payload.title
        )
    except ChatSessionNotFoundError as exc:
        return _not_found(response_formatter, str(exc))

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Chat session updated successfully',
                'session': _session_dict(session),
            }
        ),
    )


@chat_session_router.delete('/v1/chat-sessions/{session_id}')
@inject
async def delete_chat_session(
    request: Request,
    session_id: UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    chat_session_service: ChatSessionService = Depends(
        Provide[ChatbotsContainer.chat_session_service]
    ),
):
    try:
        user_id = current_user_id(request)
    except NotAUserError as exc:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    try:
        await chat_session_service.delete_session(session_id, user_id)
    except ChatSessionNotFoundError as exc:
        return _not_found(response_formatter, str(exc))

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Chat session deleted successfully'}
        ),
    )


@chat_session_router.post('/v1/chat-sessions/{session_id}/messages')
@inject
async def send_message(
    request: Request,
    session_id: UUID,
    payload: SendMessagePayload,
    stream: bool = Query(False, description='Return the reply as an SSE stream'),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    chatbot_service: ChatbotService = Depends(
        Provide[ChatbotsContainer.chatbot_service]
    ),
    chat_session_service: ChatSessionService = Depends(
        Provide[ChatbotsContainer.chat_session_service]
    ),
    chat_inference_service: ChatInferenceService = Depends(
        Provide[ChatbotsContainer.chat_inference_service]
    ),
):
    """Send a turn and get the reply.

    Order of operations matters twice here:

    The LLM is resolved before anything is written. A broken config is
    deterministic -- it will fail again on retry -- so persisting a turn that
    can never be answered would just litter the thread. Resolving first also
    means the failure can still pick a status code, which the streaming path
    loses the moment `StreamingResponse` sends its headers.

    The user's message is then committed before generation runs. That keeps the
    two rows' `created_at` values distinct without a sequence column, and it
    means a message survives a provider failure -- the case the early return
    above deliberately does not cover -- so the user can retry.
    """
    try:
        user_id = current_user_id(request)
    except NotAUserError as exc:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    try:
        session = await chat_session_service.get_owned_session(session_id, user_id)
    except ChatSessionNotFoundError as exc:
        return _not_found(response_formatter, str(exc))

    try:
        chatbot = await _require_chattable_chatbot(chatbot_service, session.chatbot_id)
    except ChatbotNotFoundError:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=response_formatter.buildErrorResponse(
                'This chatbot is no longer available; the conversation is read-only'
            ),
        )

    # Read while the request context is unambiguously current. The streamed
    # path below runs after this function has returned, and resolving the id
    # there would read whatever context happens to be current by then.
    request_id = get_current_request_id()

    try:
        llm = await chat_inference_service.resolve_llm(chatbot, str(user_id))
    except ChatInferenceError as exc:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    # Before the write, and before a status code stops being available. See
    # check_user_message: a refused turn should leave no trace in the thread,
    # and the streaming branch below can no longer report anything but an
    # in-band frame. Resolving the llm still comes first -- a broken config is
    # free to detect, and there is no sense billing a safety provider for a
    # chatbot that cannot answer either way.
    with guardrail_run_scope(request_id):
        await chat_inference_service.check_user_message(
            chatbot, payload.content, str(user_id)
        )

    user_message = await chat_session_service.add_message(
        session_id=session_id, role=ROLE_USER, content=payload.content
    )
    await chat_session_service.ensure_title(session, payload.content)

    history = await chat_session_service.get_history(session_id)

    if stream:
        return StreamingResponse(
            _stream_reply(
                chat_inference_service=chat_inference_service,
                chat_session_service=chat_session_service,
                llm=llm,
                session=session,
                history=history,
                request_id=request_id,
            ),
            media_type='text/event-stream',
            headers=SSE_HEADERS,
        )

    try:
        with guardrail_run_scope(request_id):
            content = await chat_inference_service.generate(llm, session, history)
    except GuardrailBlocked:
        # Handled at the app level, which already logs the operator detail and
        # returns the decision's caller-facing message. Caught only to keep it
        # out of the branch below, which would report a policy decision as a
        # provider failure and invite a retry that cannot succeed.
        raise
    except Exception:
        logger.exception(f'Chat inference failed for session {session_id}')
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=response_formatter.buildErrorResponse(MODEL_FAILURE_MESSAGE),
        )

    assistant_message = await chat_session_service.add_message(
        session_id=session_id, role=ROLE_ASSISTANT, content=content
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'user_message': user_message.to_dict(),
                'assistant_message': assistant_message.to_dict(),
            }
        ),
    )


async def _stream_reply(
    chat_inference_service: ChatInferenceService,
    chat_session_service: ChatSessionService,
    llm,
    session,
    history,
    request_id: str,
):
    """Yield deltas, then persist the assembled reply exactly once.

    `llm` is already built by the caller: an async generator does not execute
    until Starlette starts iterating it, which is after the 200 and the headers
    have gone out, so anything resolved in here could no longer influence the
    status code. What is left to fail below is generation itself -- provider
    timeouts and dropped connections -- which SSE cannot report in a status code
    anyway, hence the in-band error frame.

    `request_id` is passed in for the same reason, rather than read here.

    Each terminal path persists explicitly rather than sharing a `finally`,
    because the disconnect path cannot yield: cleanup runs with GeneratorExit or
    CancelledError in flight, and yielding there raises "async generator ignored
    GeneratorExit". Awaiting is allowed, yielding is not -- so the disconnect
    branch saves without emitting a final event to a socket that is gone.

    One consequence of guarding this path: when policy checks output, nothing
    is released until the whole reply has been cleared, so the deltas below
    arrive as a single chunk at the end and the reply stops being incremental.
    """
    chunks: list[str] = []

    async def persist() -> str | None:
        content = ''.join(chunks)
        if not content:
            return None
        message = await chat_session_service.add_message(
            session_id=session.id, role=ROLE_ASSISTANT, content=content
        )
        return str(message.id)

    try:
        # Scoped per step rather than around the loop: a scope held across a
        # yield resets its token in whatever context resumes the generator,
        # which on disconnect is the finaliser's, not this one. See
        # run_scoped_stream.
        async for delta in run_scoped_stream(
            chat_inference_service.stream(llm, session, history), request_id
        ):
            chunks.append(delta)
            yield f'data: {json.dumps({"content": delta})}\n\n'
    except (GeneratorExit, asyncio.CancelledError):
        # Client hung up mid-reply. Save the partial text -- the tokens were
        # already spent, and a thread ending on an unanswered question is worse
        # than one ending on a short answer.
        #
        # This saves nothing when policy checks output: buffering means no
        # delta has reached `chunks` yet, so there is no partial reply to keep.
        # The tokens are still spent, but withholding them is the point.
        #
        # Both exception types are caught because which one arrives depends on
        # how the server tears the request down: aclose() throws GeneratorExit,
        # while a cancelled request task raises CancelledError at the yield.
        #
        # The write is shielded and its own CancelledError suppressed: in the
        # cancellation case the surrounding task is already unwinding, so an
        # unshielded await would be cancelled at its first suspension point and
        # the insert would never reach the database. Shielding lets the insert
        # run to completion even though we do not get to observe the result --
        # best-effort by construction, which is the most that is available here.
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.shield(persist())
        raise
    except GuardrailBlocked as exc:
        # Nothing is persisted. A block cannot follow a delta that has already
        # been sent: inbound content is checked before the first chunk is
        # pulled, and an outbound block only happens in the buffered mode that
        # releases nothing until the whole reply has been cleared.
        if getattr(exc, 'retract', False):
            # Would mean text was released and then withdrawn -- only possible
            # under incremental release, which this consumer never opts into.
            logger.error(
                f'Guardrail asked the chat stream to retract for session '
                f'{session.id}; text may already be on screen'
            )
        # The decision's own message, not MODEL_FAILURE_MESSAGE: nothing was
        # saved and a block is not retryable, so both halves of that sentence
        # would be wrong here.
        logger.warning(f'Chat streaming blocked by policy for session {session.id}')
        yield f'data: {json.dumps({"error": str(exc)})}\n\n'
        return
    except Exception:
        # The exception itself stays in the logs -- see MODEL_FAILURE_MESSAGE.
        logger.exception(f'Chat streaming failed for session {session.id}')
        await persist()
        yield f'data: {json.dumps({"error": MODEL_FAILURE_MESSAGE})}\n\n'
        return

    message_id = await persist()
    yield f'data: {json.dumps({"done": True, "message_id": message_id})}\n\n'
