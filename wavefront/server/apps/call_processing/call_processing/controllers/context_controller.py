"""Internal endpoint floware calls while an outbound call rings.

``POST /api/calls/prepare`` keeps the context a CRM sent with the call and
starts the caller lookups, so both are ready when the caller answers. floware
dials first and passes the provider's call id, which is the id the media
stream reports, so no extra parameter travels through the telephony provider.

Auth is floware's: in production the caller must present the service mesh's
mTLS identity (``X-Forwarded-Client-Cert``) from an allowed namespace; outside
production, the passthrough secret. Unlike ``/api/cache``, production is never
left open, because call_processing is public for the telephony webhooks. The
header is only as trustworthy as the sidecar that appends to it, so production
must not expose this port outside the mesh (see ``mtls_allowed_namespaces``).
"""

import json
import re
from typing import Dict, Optional
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from call_processing.di.application_container import ApplicationContainer
from call_processing.log.logger import logger
from call_processing.services.common.context.compiler import prepare_outbound_call
from call_processing.services.common.context.store import CallContextStore
from call_processing.services.common.context.subject import CallSubject
from call_processing.services.common.voice_agent_cache_service import (
    VoiceAgentCacheService,
)

context_router = APIRouter(prefix='/calls')

MAX_CONTEXT_BYTES = 2048
_CONTEXT_KEY = re.compile(r'^[a-z0-9_]{1,40}$')
_SPIFFE_ID = re.compile(r'URI=(spiffe://[^;,"]+)')


def allowed_principal_prefixes(namespaces: Optional[str]) -> tuple:
    """SPIFFE ID prefixes for a comma-separated namespace list (as floware).

    The trailing '/' stops namespace ``api`` from also admitting ``api-evil``.
    """
    names = [n.strip() for n in (namespaces or '').split(',') if n.strip()]
    return tuple(f'spiffe://cluster.local/ns/{name}/' for name in names)


def mtls_principal(xfcc: Optional[str]) -> Optional[str]:
    """The SPIFFE ID in an ``X-Forwarded-Client-Cert`` header, if any.

    The sidecar appends the peer it authenticated as the last entry; earlier
    entries arrived as request headers and can be forged (as floware).
    """
    if not xfcc:
        return None
    uris = _SPIFFE_ID.findall(xfcc)
    if uris:
        return uris[-1]
    return xfcc if xfcc.startswith('spiffe://') else None


@inject
def verify_internal_caller(
    x_passthrough: Optional[str] = Header(None),
    x_forwarded_client_cert: Optional[str] = Header(None),
    app_env: str = Depends(Provide[ApplicationContainer.config.env_config.app_env]),
    passthrough_secret: Optional[str] = Depends(
        Provide[ApplicationContainer.config.env_config.passthrough_secret]
    ),
    mtls_allowed_namespaces: Optional[str] = Depends(
        Provide[ApplicationContainer.config.auth.mtls_allowed_namespaces]
    ),
) -> None:
    """Only floware may call: mTLS identity in production, passthrough elsewhere."""
    if (app_env or 'production') == 'production':
        prefixes = allowed_principal_prefixes(mtls_allowed_namespaces)
        principal = mtls_principal(x_forwarded_client_cert)
        if prefixes and principal and principal.startswith(prefixes):
            return
        logger.warning(
            f'Rejected /calls/prepare: principal {principal!r} not in '
            f'allowed namespaces ({len(prefixes)} configured)'
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    if passthrough_secret and x_passthrough == passthrough_secret:
        return
    logger.warning('Rejected /calls/prepare: missing or wrong X-Passthrough')
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


class PrepareCallRequest(BaseModel):
    agent_id: UUID
    # The provider's call id: the id the media stream reports
    call_ref: str = Field(..., min_length=1, max_length=128)
    customer_number: str = Field(..., min_length=1, max_length=32)
    context: Dict[str, str] = Field(default_factory=dict)

    @field_validator('context')
    @classmethod
    def _small_flat_context(cls, context: Dict[str, str]) -> Dict[str, str]:
        bad_keys = [key for key in context if not _CONTEXT_KEY.match(key)]
        if bad_keys:
            raise ValueError(f'context keys must match [a-z0-9_]{{1,40}}: {bad_keys}')
        # UTF-8 bytes of compact JSON, counted the same way floware and the client do
        size = len(
            json.dumps(context, ensure_ascii=False, separators=(',', ':')).encode()
        )
        if size > MAX_CONTEXT_BYTES:
            raise ValueError(f'context is over {MAX_CONTEXT_BYTES} bytes')
        return context


@context_router.post('/prepare', status_code=status.HTTP_202_ACCEPTED)
@inject
async def prepare_call(
    request: PrepareCallRequest,
    _auth: None = Depends(verify_internal_caller),
    call_context_store: CallContextStore = Depends(
        Provide[ApplicationContainer.call_context_store]
    ),
    voice_agent_cache_service: VoiceAgentCacheService = Depends(
        Provide[ApplicationContainer.voice_agent_cache_service]
    ),
):
    """Keep the CRM's context and start the caller lookups while the call rings."""
    subject = CallSubject.for_call(
        call_ref=request.call_ref,
        direction='outbound',
        raw_phone=request.customer_number,
    )
    saved = await prepare_outbound_call(
        voice_agent_cache_service,
        str(request.agent_id),
        subject,
        call_context_store,
        request.context,
    )
    logger.info(
        f'Prepared outbound call {request.call_ref} for agent {request.agent_id}: '
        f'context keys {sorted(request.context)}, saved={saved}'
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={'call_ref': request.call_ref, 'context_saved': saved},
    )
