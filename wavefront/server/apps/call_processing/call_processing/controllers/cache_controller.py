"""Cache management endpoints for voice agent configurations"""

import os
from uuid import UUID
from fastapi import APIRouter, HTTPException, Header, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from call_processing.log.logger import logger
from call_processing.services.voice_agent_cache_service import VoiceAgentCacheService
from call_processing.cache.cache_utils import (
    get_voice_agent_cache_key,
    get_llm_config_cache_key,
    get_tts_config_cache_key,
    get_stt_config_cache_key,
    get_telephony_config_cache_key,
)
from call_processing.constants.api_endpoints import VALID_CONFIG_TYPES
from call_processing.di.application_container import ApplicationContainer
from dependency_injector.wiring import inject, Provide

cache_router = APIRouter(prefix='/cache')


class InvalidateCacheRequest(BaseModel):
    """Request body for cache invalidation"""

    config_type: str
    config_id: UUID


def verify_passthrough_auth(x_passthrough: Optional[str] = Header(None)) -> None:
    """
    Verify passthrough authentication header.
    In non-production, validates the passthrough header.
    In production, skips validation (relies on service mesh/mTLS).

    Args:
        x_passthrough: X-Passthrough header value

    Raises:
        HTTPException: If authentication fails in non-production
    """
    app_env = os.getenv('APP_ENV', 'dev')

    # In production, skip passthrough validation (use service mesh instead)
    if app_env == 'production':
        return

    # Non-production: Strict passthrough validation
    expected_secret = os.getenv('PASSTHROUGH_SECRET')

    if not expected_secret:
        logger.warning('Passthrough not configured')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Passthrough not configured',
        )

    if not x_passthrough:
        logger.warning('Missing X-Passthrough header')
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Missing X-Passthrough header',
        )

    if x_passthrough != expected_secret:
        logger.warning('Invalid X-Passthrough header')
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid authentication credentials',
        )


@cache_router.post('/invalidate', status_code=200)
@inject
async def invalidate_cache(
    request: InvalidateCacheRequest,
    voice_agent_cache_service: VoiceAgentCacheService = Depends(
        Provide[ApplicationContainer.voice_agent_cache_service]
    ),
    _auth: None = Depends(verify_passthrough_auth),
):
    """
    Invalidate and refresh a specific config in cache

    This endpoint implements the "refresh" pattern:
    1. Remove the config from cache
    2. Fetch fresh config from floware API
    3. Store the fresh config back in cache

    Authentication: Requires X-Passthrough header

    Args:
        request: Contains config_type and config_id

    Returns:
        JSONResponse with success message

    Raises:
        HTTPException: If config_type is invalid or API fetch fails
    """
    config_type = request.config_type
    config_id = request.config_id

    # Validate config type
    if config_type not in VALID_CONFIG_TYPES:
        logger.error(f'Invalid config type: {config_type}')
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Invalid config_type. Must be one of: {", ".join(VALID_CONFIG_TYPES)}',
        )

    logger.info(f'Invalidating cache for {config_type} {config_id}')

    # Step 1: Get the appropriate cache key
    cache_key_funcs = {
        'voice_agent': get_voice_agent_cache_key,
        'llm_inference_config': get_llm_config_cache_key,
        'tts_config': get_tts_config_cache_key,
        'stt_config': get_stt_config_cache_key,
        'telephony_config': get_telephony_config_cache_key,
    }

    cache_key_func = cache_key_funcs.get(config_type)
    if cache_key_func is None:
        logger.error(f'No cache key function configured for config_type={config_type}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Cache key mapping not configured for given config_type',
        )

    cache_key = cache_key_func(config_id)

    # Step 2: Remove from cache
    removed = voice_agent_cache_service.cache_manager.remove(cache_key)
    if removed:
        logger.info(f'Removed {config_type} {config_id} from cache')
    else:
        logger.warning(f'{config_type} {config_id} was not in cache')

    # Step 3: Fetch fresh config from floware API
    try:
        if not voice_agent_cache_service.floware_http_client:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Floware HTTP client not configured',
            )

        # Special handling for voice_agent vs other configs
        if config_type == 'voice_agent':
            fresh_config = (
                await voice_agent_cache_service.floware_http_client.fetch_voice_agent(
                    config_id
                )
            )
        else:
            fresh_config = (
                await voice_agent_cache_service.floware_http_client.fetch_config(
                    config_type, config_id
                )
            )

        # If config not found, just remove from cache (don't fail)
        if not fresh_config:
            logger.info(
                f'{config_type} {config_id} not found in floware (likely deleted). '
                f'Removed from cache.'
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    'message': f'Cache invalidated for {config_type} {config_id}',
                    'config_type': config_type,
                    'config_id': str(config_id),
                    'note': 'Config not found in floware - likely deleted',
                },
            )

        # Step 4: Store fresh config back in cache
        success = voice_agent_cache_service.cache_manager.set_json(
            cache_key, fresh_config, expiry=voice_agent_cache_service.cache_ttl
        )

        if not success:
            logger.error(f'Failed to cache fresh config for {config_type} {config_id}')
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail='Failed to cache fresh config',
            )

        logger.info(f'Successfully refreshed cache for {config_type} {config_id}')

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                'message': f'Successfully invalidated and refreshed cache for {config_type} {config_id}',
                'config_type': config_type,
                'config_id': str(config_id),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'Error refreshing cache for {config_type} {config_id}: {e}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to refresh cache: {str(e)}',
        )
