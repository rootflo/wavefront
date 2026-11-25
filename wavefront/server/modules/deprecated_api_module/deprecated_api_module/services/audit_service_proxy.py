"""Forwards deprecated APIs to the API services that replace them.

This module is being deprecated: ``/v1/image/analyse`` no longer processes
images itself, it relays the caller's request unchanged to the audit service
exposed through floware's API services.
"""

from typing import Mapping

import httpx

# The upstream service's registered id; it is the one place that name appears.
AUDIT_SERVICE_PATH = '/floware/v1/api-services/gold-audit-service/apis/v1/audit'

# Hop-by-hop headers (RFC 9110 §7.6.1) and the ones httpx must compute for the
# new connection. Forwarding them would describe the inbound connection, not
# the outbound one. accept-encoding is dropped so the upstream body arrives
# uncompressed and can be returned without re-encoding.
_EXCLUDED_REQUEST_HEADERS = frozenset(
    {
        'host',
        'content-length',
        'connection',
        'keep-alive',
        'proxy-connection',
        'transfer-encoding',
        'te',
        'trailer',
        'upgrade',
        'accept-encoding',
    }
)


class AuditServiceProxy:
    def __init__(self, floware_base_url: str, timeout_seconds: float = 120.0):
        if not floware_base_url:
            raise ValueError('floware_base_url must be provided')
        self.url = floware_base_url.rstrip('/') + AUDIT_SERVICE_PATH
        self.timeout = httpx.Timeout(timeout_seconds)

    async def forward(
        self, body: bytes, headers: Mapping[str, str], query: str = ''
    ) -> httpx.Response:
        forward_headers = {
            k: v
            for k, v in headers.items()
            if k.lower() not in _EXCLUDED_REQUEST_HEADERS
        }
        url = f'{self.url}?{query}' if query else self.url
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.post(url, content=body, headers=forward_headers)
