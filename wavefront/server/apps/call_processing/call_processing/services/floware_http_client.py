"""HTTP client for making requests to floware APIs"""

import httpx
from typing import Dict, Any, Optional
from uuid import UUID

from call_processing.log.logger import logger
from call_processing.constants.api_endpoints import (
    CONFIG_TYPE_ENDPOINTS,
    VOICE_AGENT_ENDPOINT,
)
from call_processing.constants.auth import RootfloHeaders


class FlowareHttpClient:
    """HTTP client for making requests to floware APIs"""

    def __init__(
        self,
        base_url: str,
        passthrough_secret: str,
        app_env: str = 'production',
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip('/')
        self.passthrough_secret = passthrough_secret
        self.app_env = app_env
        self.timeout = timeout

    def _get_headers(self) -> Dict[str, str]:
        """
        Generate request headers with environment-aware authentication.
        Only includes passthrough header in non-production environments.
        """
        headers: Dict[str, str] = {'Content-Type': 'application/json'}

        # Add passthrough header for non-production environments
        if self.app_env != 'production' and self.passthrough_secret:
            headers[RootfloHeaders.PASSTHROUGH] = self.passthrough_secret

        return headers

    async def fetch_voice_agent(self, agent_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Fetch a voice agent from floware API

        Args:
            agent_id: UUID of the voice agent

        Returns:
            Voice agent dict if successful

        Raises:
            httpx.HTTPStatusError: If API returns 4xx/5xx error
            httpx.RequestError: If request fails (network error, timeout, etc.)

        """
        url = f'{self.base_url}{VOICE_AGENT_ENDPOINT.format(agent_id=agent_id)}'

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, headers=self._get_headers())
                response.raise_for_status()

                # Extract voice agent from response data structure
                data = response.json()
                if 'data' in data:
                    # Handle response_formatter wrapped response
                    return data['data']
                return data

            except httpx.HTTPStatusError as e:
                logger.error(
                    f'HTTP error fetching voice_agent {agent_id}: '
                    f'status={e.response.status_code}'
                )
                raise
            except httpx.RequestError as e:
                logger.error(f'Request error fetching voice_agent {agent_id}: {e}')
                raise

    async def fetch_config(
        self, config_type: str, config_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a config from floware API

        Args:
            config_type: Type of config (llm_inference_config, tts_config, etc.)
            config_id: UUID of the config

        Returns:
            Config dict if successful

        Raises:
            ValueError: If config_type is not valid
            httpx.HTTPStatusError: If API returns 4xx/5xx error
            httpx.RequestError: If request fails (network error, timeout, etc.)
        """
        endpoint = CONFIG_TYPE_ENDPOINTS.get(config_type)
        if not endpoint:
            raise ValueError(f'Invalid config type: {config_type}')

        url = f'{self.base_url}{endpoint.format(config_id=config_id)}'

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, headers=self._get_headers())
                response.raise_for_status()

                # Extract config from response_formatter wrapped response
                data = response.json()
                if 'data' in data:
                    return data['data']
                return data

            except httpx.HTTPStatusError as e:
                logger.error(
                    f'HTTP error fetching {config_type} {config_id}: '
                    f'status={e.response.status_code}'
                )
                raise
            except httpx.RequestError as e:
                logger.error(f'Request error fetching {config_type} {config_id}: {e}')
                raise
