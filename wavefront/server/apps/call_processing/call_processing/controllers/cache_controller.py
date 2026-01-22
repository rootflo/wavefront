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
    get_tools_config_cache_key,
)
from call_processing.constants.api_endpoints import VALID_CONFIG_TYPES
from call_processing.di.application_container import ApplicationContainer
from dependency_injector.wiring import inject, Provide

cache_router = APIRouter(prefix='/cache')


class InvalidateCacheRequest(BaseModel):
    """Request body for cache invalidation"""

    config_type: str
    config_id: str  # Can be UUID string or phone number for inbound_number type


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
    config_id_str = request.config_id

    # Validate config type (including inbound_number)
    valid_types = list(VALID_CONFIG_TYPES) + ['inbound_number']
    if config_type not in valid_types:
        logger.error(f'Invalid config type: {config_type}')
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Invalid config_type. Must be one of: {", ".join(valid_types)}',
        )

    logger.info(f'Invalidating cache for {config_type} {config_id_str}')

    # Step 1: Handle inbound_number separately (simple string-based cache key)
    if config_type == 'inbound_number':
        # For inbound numbers, just remove the cache key
        cache_key = f'inbound_number:{config_id_str}'
        removed = voice_agent_cache_service.cache_manager.remove(cache_key)

        if removed:
            logger.info(f'Removed inbound number cache for {config_id_str}')
        else:
            logger.warning(f'Inbound number {config_id_str} was not in cache')

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                'message': f'Cache invalidated for inbound_number {config_id_str}',
                'config_type': config_type,
                'config_id': config_id_str,
            },
        )

    # Step 2: Get the appropriate cache key for config types
    # Convert config_id string to UUID for UUID-based configs
    try:
        config_id = UUID(config_id_str)
    except ValueError:
        logger.error(f'Invalid UUID format for config_id: {config_id_str}')
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'config_id must be a valid UUID for config_type={config_type}',
        )

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

    # Step 3: Remove from cache
    removed = voice_agent_cache_service.cache_manager.remove(cache_key)
    if removed:
        logger.info(f'Removed {config_type} {config_id} from cache')
    else:
        logger.warning(f'{config_type} {config_id} was not in cache')

    # If invalidating voice_agent, also invalidate its tools cache
    if config_type == 'voice_agent':
        tools_cache_key = get_tools_config_cache_key(config_id)
        tools_removed = voice_agent_cache_service.cache_manager.remove(tools_cache_key)
        if tools_removed:
            logger.info(f'Removed tools cache for voice agent {config_id}')
        else:
            logger.warning(f'Tools cache for voice agent {config_id} was not in cache')

    # Step 4: Fetch fresh config from floware API
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

        # If voice_agent, also refresh the tools cache
        if config_type == 'voice_agent':
            try:
                tools = (
                    await voice_agent_cache_service.floware_http_client.get_agent_tools(
                        config_id
                    )
                )
                tools_cache_key = get_tools_config_cache_key(config_id)
                if tools:
                    voice_agent_cache_service.cache_manager.set_json(
                        tools_cache_key,
                        tools,
                        expiry=voice_agent_cache_service.cache_ttl,
                    )
                    logger.info(
                        f'Successfully refreshed tools cache for voice agent {config_id} ({len(tools)} tools)'
                    )
                else:
                    # Cache empty list
                    voice_agent_cache_service.cache_manager.set_json(
                        tools_cache_key, [], expiry=voice_agent_cache_service.cache_ttl
                    )
                    logger.info(f'Cached empty tools list for voice agent {config_id}')
            except Exception as e:
                # Don't fail the whole invalidation if tools refresh fails
                logger.warning(
                    f'Failed to refresh tools cache for voice agent {config_id}: {e}'
                )

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
