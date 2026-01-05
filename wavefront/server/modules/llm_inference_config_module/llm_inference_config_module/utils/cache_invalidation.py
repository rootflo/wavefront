"""Utility for invalidating cache in call_processing app"""

import os
import httpx
from uuid import UUID
from common_module.log.logger import logger


async def invalidate_call_processing_cache(
    config_type: str,
    config_id: UUID,
    operation: str = 'update',
) -> bool:
    """
    Invalidate cache in call_processing app

    Args:
        config_type: Type of config (llm_inference_config)
        config_id: UUID of the config
        operation: Operation type (create, update, or delete)

    Returns:
        True if successful, False otherwise (never raises exceptions)
        Logs warnings on failures but doesn't break the main operation
    """
    call_processing_base_url = os.getenv('CALL_PROCESSING_BASE_URL')
    passthrough_secret = os.getenv('PASSTHROUGH_SECRET')

    if not call_processing_base_url or not passthrough_secret:
        logger.warning(
            f'Cache invalidation skipped for {config_type} {config_id}: '
            f'CALL_PROCESSING_BASE_URL or PASSTHROUGH_SECRET not configured'
        )
        return False

    url = f'{call_processing_base_url.rstrip("/")}/api/cache/invalidate'
    headers = {
        'Content-Type': 'application/json',
        'X-Passthrough': passthrough_secret,
    }
    payload = {'config_type': config_type, 'config_id': str(config_id)}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload, headers=headers)

            if response.status_code in [200, 201]:
                logger.info(
                    f'Successfully invalidated cache for {config_type} {config_id} '
                    f'(operation: {operation})'
                )
                return True
            else:
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
            f'Cache invalidation request error for {config_type} {config_id}: {e}. '
            f'Continuing with main operation.'
        )
        return False
    except Exception as e:
        logger.warning(
            f'Unexpected error during cache invalidation for {config_type} {config_id}: {e}. '
            f'Continuing with main operation.',
            exc_info=True,
        )
        return False
