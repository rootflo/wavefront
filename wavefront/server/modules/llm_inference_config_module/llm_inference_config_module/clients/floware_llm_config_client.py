"""Reads LLM inference configs from floware for services without KMS access."""

from typing import Any, Dict, Optional
from uuid import UUID

import flo_lib.http as httpx


class FlowareLlmConfigClient:
    """Fetches an LLM inference config with its plaintext api_key from floware.

    Stands in for `LlmInferenceConfigService` where only `get_runtime_config`
    is used (the celery worker), so floware stays the only KMS holder. Nothing
    is cached: a rotated key takes effect on the next call.
    """

    def __init__(
        self,
        base_url: str,
        passthrough_secret: Optional[str],
        app_env: str = 'production',
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip('/')
        self.passthrough_secret = passthrough_secret
        self.app_env = app_env
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        # Never an Authorization header: floware returns secrets only on the
        # service path (mTLS in production, passthrough elsewhere), and a bearer
        # token would send the request down the user JWT path instead.
        headers = {'Content-Type': 'application/json'}
        if self.app_env != 'production' and self.passthrough_secret:
            headers['X-Passthrough'] = self.passthrough_secret
        return headers

    async def get_runtime_config(self, config_id: UUID) -> Optional[Dict[str, Any]]:
        """Return the stored config with its plaintext api_key, or None if missing.

        Raises:
            httpx.HTTPStatusError: floware answered with an error other than 404
            httpx.RequestError: floware could not be reached
        """
        url = f'{self.base_url}/floware/v1/llm-inference-configs/{config_id}'
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                url,
                params={'include_secrets': 'true'},
                headers=self._headers(),
            )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json().get('data')
