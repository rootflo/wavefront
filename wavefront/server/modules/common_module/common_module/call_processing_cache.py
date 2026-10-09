"""Client for invalidating cached configs in the call_processing app."""

from uuid import UUID

import flo_lib.http as httpx

from common_module.log.logger import logger


class CallProcessingCacheInvalidator:
    """Tells call_processing to drop a cached config after it changes here.

    Built once from the app's runtime settings and injected into the services
    that mutate those configs. Invalidation is best-effort: ``invalidate`` never
    raises, so a call_processing outage cannot fail the write that triggered it.
    """

    def __init__(
        self,
        call_processing_base_url: str | None,
        passthrough_secret: str | None,
        timeout: float = 10.0,
    ):
        self.call_processing_base_url = call_processing_base_url
        self.passthrough_secret = passthrough_secret
        self.timeout = timeout

    async def invalidate(
        self,
        config_type: str,
        config_id: UUID | str,
        operation: str = 'update',
    ) -> bool:
        """Invalidate one cached config in call_processing.

        Args:
            config_type: Type of config (voice_agent, tts_config, stt_config,
                telephony_config, inbound_number, llm_inference_config, ...)
            config_id: UUID of the config, or a string identifier such as the
                phone number for ``inbound_number``
            operation: create, update or delete (used for logging only)

        Returns:
            True on success, False otherwise. Failures are logged as warnings.
        """
        if not self.call_processing_base_url:
            logger.warning(
                f'Cache invalidation skipped for {config_type} {config_id}: '
                f'call_processing_base_url not configured'
            )
            return False

        url = f'{self.call_processing_base_url.rstrip("/")}/api/cache/invalidate'
        # Passthrough is local-only; production relies on the service mesh.
        headers = {'Content-Type': 'application/json'}
        if self.passthrough_secret:
            headers['X-Passthrough'] = self.passthrough_secret
        resource_id = str(config_id) if isinstance(config_id, UUID) else config_id
        payload = {'config_type': config_type, 'config_id': resource_id}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)

            if response.status_code in (200, 201):
                logger.info(
                    f'Successfully invalidated cache for {config_type} {config_id} '
                    f'(operation: {operation})'
                )
                return True

            logger.warning(
                f'Cache invalidation failed for {config_type} {config_id}: '
                f'HTTP {response.status_code} - {response.text}'
            )
            return False

        except httpx.TimeoutException as e:
            logger.warning(
                f'Cache invalidation timeout for {config_type} {config_id}: {e}. '
                f'Continuing with main operation.'
            )
            return False
        except httpx.RequestError as e:
            logger.warning(
                f'Cache invalidation request error for {config_type} {config_id}: '
                f'{e}. Continuing with main operation.'
            )
            return False
        except Exception as e:
            logger.warning(
                f'Unexpected error during cache invalidation for {config_type} '
                f'{config_id}: {e}. Continuing with main operation.',
                exc_info=True,
            )
            return False
