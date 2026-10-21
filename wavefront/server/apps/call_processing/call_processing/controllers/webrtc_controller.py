"""WebRTC (browser) signaling endpoints.

- ``POST /api/webrtc/rooms``  floware (passthrough): create a room + one-time join token
- ``POST /api/webrtc/offer``  browser: SDP offer; ``request_data`` carries the join credentials
- ``PATCH /api/webrtc/offer`` browser: trickle ICE candidates (must hit the same instance)

Errors the browser acts on carry a stable code:
``{"error": "<code>", "message": "..."}`` with ``invalid_join_token`` (401),
``room_expired`` (410), ``room_already_joined`` (409) or ``sticky_required`` (409).
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from pipecat.transports.smallwebrtc.request_handler import IceCandidate

from call_processing.app_settings import CallProcessingAppSettings
from call_processing.controllers.cache_controller import verify_passthrough_auth
from call_processing.di.application_container import ApplicationContainer
from call_processing.log.logger import logger
from call_processing.services.webrtc_room_service import (
    WebRTCRoomError,
    WebRTCRoomService,
)
from call_processing.services.webrtc_session_service import (
    OfferRequest,
    WebRTCSessionService,
)

webrtc_router = APIRouter(prefix='/webrtc')

# Cookie an ingress can use for sticky routing of /offer (peer connections are
# held in-process on the instance that handled the offer).
AFFINITY_COOKIE = 'wf_webrtc_affinity'


class CreateRoomRequest(BaseModel):
    voice_agent_id: UUID
    # Agents the browser may hot-swap to mid-session. Decided by floware (the
    # browser only ever holds the join token); the initial agent is always allowed.
    allowed_agent_ids: Optional[List[UUID]] = None
    # True: the app drives the language via set_context.language, so the agent
    # gets no language-switching rules / detect_and_switch_language tool.
    room_context_handles_language: bool = False
    # False: a swapped-in agent starts with a clean context instead of inheriting
    # the conversation so far.
    carry_history_on_swap: bool = True


class OfferBody(BaseModel):
    model_config = ConfigDict(extra='ignore', populate_by_name=True)

    sdp: str
    type: str
    pc_id: Optional[str] = None
    restart_pc: Optional[bool] = Field(
        default=None, validation_alias=AliasChoices('restart_pc', 'restartPc')
    )
    request_data: Optional[Dict[str, Any]] = Field(
        default=None, validation_alias=AliasChoices('request_data', 'requestData')
    )


class IceCandidateBody(BaseModel):
    model_config = ConfigDict(extra='ignore')

    candidate: str
    sdp_mid: str = Field(validation_alias=AliasChoices('sdp_mid', 'sdpMid'))
    sdp_mline_index: int = Field(
        validation_alias=AliasChoices('sdp_mline_index', 'sdpMLineIndex')
    )


class IcePatchBody(BaseModel):
    model_config = ConfigDict(extra='ignore')

    pc_id: str
    candidates: List[IceCandidateBody]


def _error_response(error: WebRTCRoomError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={'error': error.code, 'message': error.message},
    )


def _set_affinity_cookie(response: Response, instance_id: str, app_env: str) -> None:
    secure = app_env != 'dev'
    response.set_cookie(
        AFFINITY_COOKIE,
        instance_id,
        max_age=3600,
        httponly=True,
        secure=secure,
        # Cross-site (console -> call_processing) needs SameSite=None, which requires Secure
        samesite='none' if secure else 'lax',
    )


@webrtc_router.post('/rooms', status_code=status.HTTP_201_CREATED)
@inject
async def create_room(
    body: CreateRoomRequest,
    room_service: WebRTCRoomService = Depends(
        Provide[ApplicationContainer.webrtc_room_service]
    ),
    app_settings: CallProcessingAppSettings = Depends(
        Provide[ApplicationContainer.app_settings]
    ),
    _auth: None = Depends(verify_passthrough_auth),
):
    """Create a room for a voice agent. The ``join_token`` is returned once."""
    room = room_service.create_room(
        str(body.voice_agent_id),
        allowed_agent_ids=[str(a) for a in body.allowed_agent_ids or []],
        room_context_handles_language=body.room_context_handles_language,
        carry_history_on_swap=body.carry_history_on_swap,
    )
    return {
        'room_id': room.room_id,
        'voice_agent_id': room.voice_agent_id,
        'join_token': room.join_token,
        'signaling_url': app_settings.webrtc.signaling_public_url,
    }


@webrtc_router.post('/offer')
@inject
async def offer(
    body: OfferBody,
    response: Response,
    session_service: WebRTCSessionService = Depends(
        Provide[ApplicationContainer.webrtc_session_service]
    ),
    app_env: str = Depends(Provide[ApplicationContainer.config.env_config.app_env]),
):
    """SDP offer from the browser. Consumes the one-time join token."""
    request_data = body.request_data or {}
    try:
        answer = await session_service.handle_offer(
            OfferRequest(
                sdp=body.sdp,
                type=body.type,
                pc_id=body.pc_id,
                restart_pc=body.restart_pc,
                room_id=request_data.get('room_id'),
                voice_agent_id=request_data.get('voice_agent_id'),
                join_token=request_data.get('join_token'),
            )
        )
    except WebRTCRoomError as e:
        logger.info(f'WebRTC offer rejected: {e.code}')
        return _error_response(e)

    _set_affinity_cookie(response, session_service.instance_id, app_env)
    return answer


@webrtc_router.patch('/offer', status_code=status.HTTP_200_OK)
@inject
async def ice_candidates(
    body: IcePatchBody,
    session_service: WebRTCSessionService = Depends(
        Provide[ApplicationContainer.webrtc_session_service]
    ),
):
    """Trickle ICE. Returns 409 ``sticky_required`` if this instance doesn't own the connection."""
    try:
        await session_service.handle_ice_candidates(
            body.pc_id,
            [
                IceCandidate(
                    candidate=c.candidate,
                    sdp_mid=c.sdp_mid,
                    sdp_mline_index=c.sdp_mline_index,
                )
                for c in body.candidates
            ],
        )
    except WebRTCRoomError as e:
        logger.info(f'WebRTC ICE rejected: {e.code}')
        return _error_response(e)
    return {'status': 'success'}
