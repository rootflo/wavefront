"""Browser (WebRTC) sessions: signaling, peer-connection ownership and lifecycle.

``SmallWebRTCRequestHandler`` / aiortc keep ``RTCPeerConnection`` state in this
process, so a session is pinned to the instance that handled its offer. ICE
(PATCH) and renegotiation must reach the same instance (sticky routing); Redis
only holds the shared room metadata (see ``WebRTCRoomService``).

Lifecycle of a session:
    offer (token consumed) -> peer connects -> pipeline runs -> cleanup
Cleanup always runs once, whether the client hung up, the connection never came
up, the idle timeout fired, the max duration elapsed or the server is shutting
down. It cancels any in-flight agent swap, closes the peer connection and ends
the room.

Agent hot-swap (browser ``switch_agent``): the session hands the pipeline a
``SwapOptions`` (the room's allowlist, the config loader, a callback that
records the swap on the room). The swap runs inside the live pipeline, so the
peer connection, the idle watchdog and the max-duration timer below are not
touched or reset by it.
"""

from __future__ import annotations

import asyncio
import socket
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
from pipecat.transports.smallwebrtc.request_handler import (
    IceCandidate,
    SmallWebRTCPatchRequest,
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from call_processing.app_settings import CallProcessingAppSettings
from call_processing.log.logger import logger
from call_processing.services.common.voice_agent_cache_service import (
    VoiceAgentCacheService,
)
from call_processing.services.webrtc.agent_swap import (
    AgentSwapController,
    SessionHooks,
    SwapOptions,
)
from call_processing.services.webrtc.conversation import WebRTCConversation
from call_processing.services.webrtc.room_service import (
    ERR_INVALID_JOIN_TOKEN,
    ERR_STICKY_REQUIRED,
    WebRTCRoomError,
    WebRTCRoomService,
    room_error,
)

# 5 minutes without speaking activity ends the session (Pipecat idle timeout)
IDLE_TIMEOUT_SECS = 300


@dataclass
class OfferRequest:
    sdp: str
    type: str
    pc_id: Optional[str] = None
    restart_pc: Optional[bool] = None
    room_id: Optional[str] = None
    voice_agent_id: Optional[str] = None
    join_token: Optional[str] = None


@dataclass
class _Session:
    room_id: str
    voice_agent_id: str
    connection: SmallWebRTCConnection
    connected: asyncio.Event = field(default_factory=asyncio.Event)
    task: Optional[asyncio.Task] = None
    cleaned_up: bool = False
    # Set by the pipeline once it is up (None until then / if swapping is off)
    swap_controller: Optional[AgentSwapController] = None
    # Background warm-up of swap targets' configs (held so it is not GC'd mid-run)
    prefetch_task: Optional[asyncio.Task] = None

    @property
    def pc_id(self) -> str:
        return self.connection.pc_id


class WebRTCSessionService:
    def __init__(
        self,
        room_service: WebRTCRoomService,
        voice_agent_cache_service: VoiceAgentCacheService,
        app_settings: CallProcessingAppSettings,
    ):
        self.room_service = room_service
        self.voice_agent_cache_service = voice_agent_cache_service
        self.app_settings = app_settings
        self.webrtc_settings = app_settings.webrtc

        # Identifies this replica in the sticky cookie and on the room record
        self.instance_id = f'{socket.gethostname()}-{uuid.uuid4().hex[:8]}'

        ice_servers: List[IceServer] = [
            IceServer(urls=url) for url in self.webrtc_settings.ice_servers
        ]
        self._handler = SmallWebRTCRequestHandler(ice_servers=ice_servers or None)
        # pc_id -> session, only for peer connections owned by this process
        self._sessions: Dict[str, _Session] = {}

    # ------------------------------------------------------------------ signaling

    async def handle_offer(self, offer: OfferRequest) -> Dict[str, str]:
        """Handle the SDP offer. Returns the SDP answer (with ``pc_id``).

        Raises ``WebRTCRoomError`` for join failures (invalid token, expired,
        already joined, wrong instance).
        """
        request = SmallWebRTCRequest(
            sdp=offer.sdp,
            type=offer.type,
            pc_id=offer.pc_id,
            restart_pc=offer.restart_pc,
        )

        if offer.pc_id:
            return await self._renegotiate(request, offer)

        voice_agent_id = self._parse_agent_id(offer.voice_agent_id)

        # Validates the token, rejects a double join, and consumes the token atomically
        self.room_service.consume_join_token(
            offer.room_id or '', voice_agent_id, offer.join_token
        )
        room_id = str(offer.room_id)

        try:
            configs = await self.voice_agent_cache_service.get_all_agent_configs(
                UUID(voice_agent_id), require_telephony=False
            )

            captured: Dict[str, SmallWebRTCConnection] = {}

            async def on_connection(connection: SmallWebRTCConnection) -> None:
                captured['connection'] = connection

            answer = await self._handler.handle_web_request(request, on_connection)
            connection = captured.get('connection')
            if not answer or connection is None:
                raise RuntimeError('WebRTC connection was not created')
        except Exception:
            # The token is spent; the client must create a new room
            self.room_service.end_room(room_id)
            raise

        session = _Session(
            room_id=room_id, voice_agent_id=voice_agent_id, connection=connection
        )
        self._sessions[session.pc_id] = session
        self._watch_connection_state(session)
        self.room_service.attach_connection(room_id, session.pc_id, self.instance_id)
        session.task = asyncio.create_task(
            self._run_session(session, configs), name=f'webrtc-session-{room_id}'
        )
        logger.info(
            f'WebRTC session started room={room_id} pc_id={session.pc_id} '
            f'instance={self.instance_id}'
        )
        return answer

    async def _renegotiate(
        self, request: SmallWebRTCRequest, offer: OfferRequest
    ) -> Dict[str, str]:
        session = self._sessions.get(offer.pc_id or '')
        if session is None:
            # Peer connections live in-process: this replica does not own it
            raise WebRTCRoomError(
                ERR_STICKY_REQUIRED,
                409,
                'This connection is handled by another instance',
            )
        if offer.room_id and offer.room_id != session.room_id:
            raise room_error(ERR_INVALID_JOIN_TOKEN)

        async def noop(_connection: SmallWebRTCConnection) -> None:
            return None

        answer = await self._handler.handle_web_request(request, noop)

        # ``restart_pc`` makes pipecat build a new peer connection with a NEW
        # pc_id. The client then PATCHes/renegotiates with the id from this
        # answer, so re-key the session or those calls 409 ``sticky_required``.
        new_pc_id = (answer or {}).get('pc_id')
        old_pc_id = offer.pc_id
        if new_pc_id and old_pc_id and new_pc_id != old_pc_id:
            # Write the room first: if it fails, the old id stays mapped locally
            self.room_service.attach_connection(
                session.room_id, new_pc_id, self.instance_id
            )
            self._sessions.pop(old_pc_id, None)
            self._sessions[new_pc_id] = session
            # The handler re-keys its own map but leaves the stale id behind
            getattr(self._handler, '_pcs_map', {}).pop(old_pc_id, None)
            logger.info(
                f'WebRTC peer connection restarted room={session.room_id} '
                f'pc_id={old_pc_id}->{new_pc_id}'
            )
        return answer

    async def handle_ice_candidates(
        self, pc_id: str, candidates: List[IceCandidate]
    ) -> None:
        if pc_id not in self._sessions:
            raise WebRTCRoomError(
                ERR_STICKY_REQUIRED,
                409,
                'This connection is handled by another instance',
            )
        await self._handler.handle_patch_request(
            SmallWebRTCPatchRequest(pc_id=pc_id, candidates=candidates)
        )

    # ------------------------------------------------------------------ lifecycle

    def _watch_connection_state(self, session: _Session) -> None:
        connection = session.connection

        async def on_connected(_connection):
            session.connected.set()

        async def on_dead(_connection):
            # Never connected (ICE failed / client left early): the pipeline is
            # still waiting for a client, so stop it. Once connected, the
            # transport's own disconnect handler ends the pipeline gracefully.
            if (
                not session.connected.is_set()
                and not session.cleaned_up
                and session.task
            ):
                session.task.cancel()

        connection.add_event_handler('connected', on_connected)
        connection.add_event_handler('failed', on_dead)
        connection.add_event_handler('closed', on_dead)

    async def _run_session(self, session: _Session, configs: Dict[str, Any]) -> None:
        settings = self.webrtc_settings
        watchdog = asyncio.create_task(self._connect_watchdog(session))
        try:
            transport = SmallWebRTCTransport(
                webrtc_connection=session.connection,
                params=TransportParams(
                    audio_in_enabled=True,
                    audio_out_enabled=True,
                ),
            )
            conversation = WebRTCConversation(
                self.app_settings,
                room_id=session.room_id,
                sample_rate=settings.sample_rate,
                idle_timeout_secs=IDLE_TIMEOUT_SECS,
                session_hooks=self._session_hooks(session, initial_configs=configs),
                room_context_handles_language=(
                    self.room_service.get_room_context_handles_language(session.room_id)
                ),
            )
            await asyncio.wait_for(
                conversation.run(transport, configs),
                timeout=settings.max_session_secs,
            )
        except asyncio.TimeoutError:
            logger.info(
                f'WebRTC room {session.room_id} hit the {settings.max_session_secs}s '
                'max session duration'
            )
        except asyncio.CancelledError:
            logger.info(f'WebRTC session {session.room_id} cancelled')
        except Exception as e:
            logger.error(f'WebRTC session {session.room_id} failed: {e}', exc_info=True)
        finally:
            watchdog.cancel()
            await self._cleanup(session)

    def _session_hooks(
        self,
        session: _Session,
        *,
        initial_configs: Optional[Dict[str, Any]] = None,
    ) -> SessionHooks:
        """What the live pipeline needs to hot-swap agents for this room."""
        # The allowlist lives on the room (set by floware); the initial agent is
        # always allowed. The browser can never widen it.
        allowed = set(self.room_service.get_allowed_agent_ids(session.room_id))
        allowed.add(session.voice_agent_id)

        # Warm configs for allowlisted swap targets so mid-call switches skip Redis/API.
        config_cache: Dict[str, Dict[str, Any]] = {}
        if initial_configs is not None:
            config_cache[session.voice_agent_id] = initial_configs

        async def load_agent_configs(agent_id: UUID) -> Dict[str, Any]:
            return await self.voice_agent_cache_service.get_all_agent_configs(
                agent_id, require_telephony=False
            )

        def on_agent_switched(agent_id: str) -> None:
            self.room_service.record_swap(session.room_id, agent_id)

        def on_ready(controller: Optional[AgentSwapController]) -> None:
            session.swap_controller = controller
            # Prefetch remaining allowlisted agents in the background.
            others = [aid for aid in allowed if aid not in config_cache]
            if others:
                session.prefetch_task = asyncio.create_task(
                    self._prefetch_swap_targets(others, config_cache),
                    name=f'webrtc-prefetch-{session.room_id}',
                )

        return SessionHooks(
            swap=SwapOptions(
                allowed_agent_ids=allowed,
                load_agent_configs=load_agent_configs,
                on_agent_switched=on_agent_switched,
                carry_history=self.room_service.get_carry_history_on_swap(
                    session.room_id
                ),
                config_cache=config_cache,
            ),
            on_ready=on_ready,
        )

    async def _prefetch_swap_targets(
        self, agent_ids: List[str], config_cache: Dict[str, Dict[str, Any]]
    ) -> None:
        try:
            warmed = await self.voice_agent_cache_service.prefetch_agent_configs(
                agent_ids, require_telephony=False
            )
            config_cache.update(warmed)
            if warmed:
                logger.info(
                    f'Prefetched configs for {len(warmed)} swap target(s): '
                    f'{list(warmed)}'
                )
        except Exception as e:
            logger.warning(f'Swap-target config prefetch failed: {e}')

    async def _connect_watchdog(self, session: _Session) -> None:
        """End sessions whose peer connection never comes up."""
        timeout = self.webrtc_settings.connect_timeout_secs
        try:
            await asyncio.wait_for(session.connected.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(
                f'WebRTC room {session.room_id} did not connect within {timeout}s'
            )
            if session.task:
                session.task.cancel()
        except asyncio.CancelledError:
            pass

    async def _cleanup(self, session: _Session) -> None:
        if session.cleaned_up:
            return
        session.cleaned_up = True
        if session.prefetch_task and not session.prefetch_task.done():
            session.prefetch_task.cancel()
        controller = session.swap_controller
        if controller is not None:
            try:
                # A swap mid-flight is abandoned; this stays the single exit path
                await controller.close()
            except Exception as e:
                logger.warning(f'Error cancelling agent swap {session.room_id}: {e}')
        try:
            await session.connection.disconnect()
        except Exception as e:
            logger.warning(f'Error closing WebRTC connection {session.pc_id}: {e}')
        self.room_service.end_room(session.room_id)
        # Dropped last so ``active_sessions == 0`` means the room is fully gone
        self._sessions.pop(session.pc_id, None)
        logger.info(f'WebRTC session cleaned up room={session.room_id}')

    async def close(self) -> None:
        """Stop every session owned by this process (application shutdown)."""
        sessions = list(self._sessions.values())
        tasks = [s.task for s in sessions if s.task and not s.task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self._handler.close()

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _parse_agent_id(voice_agent_id: Optional[str]) -> str:
        try:
            return str(UUID(str(voice_agent_id)))
        except ValueError:
            raise room_error(ERR_INVALID_JOIN_TOKEN)

    @property
    def active_sessions(self) -> int:
        return len(self._sessions)
