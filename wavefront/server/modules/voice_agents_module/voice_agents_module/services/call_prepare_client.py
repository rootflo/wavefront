"""Client for call_processing's ``POST /api/calls/prepare``.

Called right after an outbound call is placed, while it rings: call_processing
keeps the CRM's context for the call and starts the caller lookups, so both are
ready when the caller answers. The call is keyed by the provider's call id,
which is the id the media stream reports.

Best-effort and quick: ``prepare`` never raises and gives up after a short
timeout, so a call_processing problem never stops a call that is already
ringing; that call just starts without the context.
"""

from typing import Dict, Optional
from uuid import UUID

import flo_lib.http as httpx

from common_module.log.logger import logger

PREPARE_TIMEOUT_S = 1.0


class CallPrepareClient:
    def __init__(
        self,
        call_processing_base_url: Optional[str],
        passthrough_secret: Optional[str],
        timeout: float = PREPARE_TIMEOUT_S,
    ):
        self.call_processing_base_url = (call_processing_base_url or '').rstrip('/')
        self.passthrough_secret = passthrough_secret or None
        self.timeout = timeout

    async def prepare(
        self,
        agent_id: UUID,
        call_ref: str,
        customer_number: str,
        context: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Hand the ringing call to call_processing; False (logged) on any failure."""
        # Smartflo reports 'unknown' when it has no id: every such call would
        # share one key, so skip rather than mix callers' context
        if not self.call_processing_base_url or call_ref in ('', 'unknown'):
            logger.warning(
                f'Call prepare skipped for call {call_ref!r}: '
                'call_processing_base_url or call id missing'
            )
            return False

        url = f'{self.call_processing_base_url}/api/calls/prepare'
        # Passthrough is local-only; production authenticates by mTLS identity
        headers = {'Content-Type': 'application/json'}
        if self.passthrough_secret:
            headers['X-Passthrough'] = self.passthrough_secret
        payload = {
            'agent_id': str(agent_id),
            'call_ref': call_ref,
            'customer_number': customer_number,
            'context': context or {},
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except Exception as e:
            logger.warning(f'Call prepare failed for call {call_ref}: {e}')
            return False

        if response.status_code == 202:
            logger.info(
                f'Call prepared: call {call_ref}, context keys {sorted(context or {})}'
            )
            return True
        logger.warning(
            f'Call prepare failed for call {call_ref}: HTTP {response.status_code}'
        )
        return False
