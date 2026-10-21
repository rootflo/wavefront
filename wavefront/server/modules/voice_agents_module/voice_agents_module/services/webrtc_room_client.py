"""Client for call_processing's browser (WebRTC) room and signaling routes.

Floware owns the authenticated product API; call_processing owns the room
registry and the media. This client:

- creates rooms (``POST /api/webrtc/rooms``, passthrough-authenticated)
- optionally proxies the browser's SDP offer / ICE requests, for deployments
  where call_processing is not reachable from browsers
"""

from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie
from typing import Any, Dict, List, Optional
from uuid import UUID

import flo_lib.http as httpx

from common_module.log.logger import logger

# Floware-relative base the browser uses when signaling goes through floware.
# The console gateway serves floware under /v1/{appId}, so the client resolves it there.
FLOWARE_SIGNALING_PATH = '/floware/v1/webrtc'

AFFINITY_COOKIE_NAME = 'wf_webrtc_affinity'


def _extract_affinity_cookie(cookie_header: Optional[str]) -> Optional[str]:
    """Return only the affinity cookie as ``name=value``; never other browser cookies."""
    if not cookie_header:
        return None
    parsed: SimpleCookie = SimpleCookie()
    try:
        parsed.load(cookie_header)
    except CookieError:
        return None
    morsel = parsed.get(AFFINITY_COOKIE_NAME)
    if morsel is None or not morsel.value:
        return None
    return f'{AFFINITY_COOKIE_NAME}={morsel.value}'


class WebRTCRoomClientError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class ProxiedResponse:
    status_code: int
    content: bytes
    media_type: str
    set_cookie: Optional[str] = None


class WebRTCRoomClient:
    def __init__(
        self,
        call_processing_base_url: Optional[str],
        passthrough_secret: Optional[str],
        signaling_via_floware: bool = False,
        timeout: float = 15.0,
    ):
        self.call_processing_base_url = (call_processing_base_url or '').rstrip('/')
        self.passthrough_secret = passthrough_secret or None
        self.signaling_via_floware = signaling_via_floware
        self.timeout = timeout

    def _require_base_url(self) -> str:
        if not self.call_processing_base_url:
            raise WebRTCRoomClientError(
                'call_processing_base_url is not configured', status_code=503
            )
        return self.call_processing_base_url

    async def create_room(
        self,
        voice_agent_id: UUID,
        allowed_agent_ids: Optional[List[UUID]] = None,
        room_context_handles_language: bool = False,
        carry_history_on_swap: bool = True,
    ) -> Dict[str, Any]:
        """Create a room. Returns room_id, voice_agent_id, join_token, signaling_url.

        ``allowed_agent_ids`` is the allowlist for hot-swapping the voice agent
        mid-session (call_processing always adds the initial agent). Omit it for a
        room that cannot switch agents.

        ``room_context_handles_language`` is only sent when true (the default
        keeps native language switching, and older call_processing instances
        never see the field). ``carry_history_on_swap`` is likewise only sent when
        false (the default carries the conversation over to the new agent).

        With ``signaling_via_floware`` the returned ``signaling_url`` is the
        floware-relative proxy path (and ``signaling_via_floware`` is true), so
        browsers never need to reach call_processing.
        """
        url = f'{self._require_base_url()}/api/webrtc/rooms'
        # Passthrough is local-only; production relies on the service mesh.
        headers = {'Content-Type': 'application/json'}
        if self.passthrough_secret:
            headers['X-Passthrough'] = self.passthrough_secret

        body: Dict[str, Any] = {'voice_agent_id': str(voice_agent_id)}
        if allowed_agent_ids is not None:
            body['allowed_agent_ids'] = [str(a) for a in allowed_agent_ids]
        if room_context_handles_language:
            body['room_context_handles_language'] = True
        if not carry_history_on_swap:
            body['carry_history_on_swap'] = False

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=body, headers=headers)
        except httpx.RequestError as e:
            logger.error(f'WebRTC room creation request failed: {e}')
            raise WebRTCRoomClientError('Voice service is unreachable', 502) from e

        if response.status_code != 201:
            logger.error(
                f'WebRTC room creation failed: HTTP {response.status_code} '
                f'{response.text}'
            )
            raise WebRTCRoomClientError('Failed to create voice room', 502)

        room = response.json()
        if self.signaling_via_floware:
            room['signaling_url'] = FLOWARE_SIGNALING_PATH
        room['signaling_via_floware'] = self.signaling_via_floware
        return room

    async def forward_signaling(
        self, method: str, body: bytes, cookie: Optional[str]
    ) -> ProxiedResponse:
        """Forward the browser's SDP offer (POST) / ICE (PATCH) to call_processing.

        Only the sticky-affinity cookie is forwarded upstream (and its Set-Cookie back) so an ingress in front of
        call_processing keeps the browser pinned to one replica.
        """
        if not self.signaling_via_floware:
            raise WebRTCRoomClientError(
                'WebRTC signaling via floware is disabled', status_code=404
            )
        url = f'{self._require_base_url()}/api/webrtc/offer'
        headers = {'Content-Type': 'application/json'}
        affinity_cookie = _extract_affinity_cookie(cookie)
        if affinity_cookie:
            headers['Cookie'] = affinity_cookie

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method, url, content=body, headers=headers
                )
        except httpx.RequestError as e:
            logger.error(f'WebRTC signaling proxy failed: {e}')
            raise WebRTCRoomClientError('Voice service is unreachable', 502) from e

        return ProxiedResponse(
            status_code=response.status_code,
            content=response.content,
            media_type=response.headers.get('content-type', 'application/json'),
            set_cookie=response.headers.get('set-cookie'),
        )
