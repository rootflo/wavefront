"""Voice agent cache service for fetching configs from Redis"""

import asyncio
from typing import Dict, Any, List, Tuple, Optional
from uuid import UUID

from call_processing.cache.cache_manager import CacheManager
from call_processing.cache.cache_utils import (
    get_voice_agent_cache_key,
    get_llm_config_cache_key,
    get_tts_config_cache_key,
    get_stt_config_cache_key,
    get_telephony_config_cache_key,
)
from call_processing.log.logger import logger
from call_processing.services.floware_http_client import FlowareHttpClient
from fastapi import HTTPException


class VoiceAgentCacheService:
    """Service for fetching voice agent configurations from Redis cache"""

    def __init__(
        self,
        cache_manager: CacheManager,
        floware_http_client: Optional[FlowareHttpClient] = None,
    ):
        self.cache_manager = cache_manager
        self.floware_http_client = floware_http_client
        self.cache_ttl = 3600 * 24

    async def _fetch_missing_configs_from_api(
        self, missing_configs: List[Tuple[str, UUID]]
    ) -> Dict[str, Any]:
        """
        Fetch missing configs from floware API in parallel

        Args:
            missing_configs: List of (config_type, config_id) tuples

        Returns:
            Dict mapping config_type to fetched config data

        Raises:
            HTTPException: If any API call fails
        """
        if not self.floware_http_client:
            raise HTTPException(
                status_code=500,
                detail='Floware HTTP client not configured for API fallback',
            )

        # Create parallel fetch tasks
        tasks = [
            self.floware_http_client.fetch_config(config_type, config_id)
            for config_type, config_id in missing_configs
        ]

        try:
            # Execute all fetches in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check for errors
            configs = {}
            errors = []

            for (config_type, config_id), result in zip(missing_configs, results):
                if isinstance(result, Exception):
                    error_msg = f'{config_type} {config_id}: {str(result)}'
                    errors.append(error_msg)
                    logger.error(f'Failed to fetch {error_msg}')
                elif result is None:
                    error_msg = f'{config_type} {config_id} not found (404)'
                    errors.append(error_msg)
                    logger.error(f'Config not found: {error_msg}')
                else:
                    configs[config_type] = result
                    logger.info(
                        f'Successfully fetched {config_type} {config_id} from API'
                    )

            if errors:
                raise HTTPException(
                    status_code=404,
                    detail=f"Failed to fetch configs from API: {', '.join(errors)}",
                )

            return configs

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f'Error in parallel config fetch: {e}', exc_info=True)
            raise

    def _cache_config(
        self, config_type: str, config_id: UUID, config_data: Dict
    ) -> None:
        """Cache a config with appropriate key"""
        cache_key_funcs = {
            'llm_inference_config': get_llm_config_cache_key,
            'tts_config': get_tts_config_cache_key,
            'stt_config': get_stt_config_cache_key,
            'telephony_config': get_telephony_config_cache_key,
        }

        cache_key_func = cache_key_funcs.get(config_type)
        if cache_key_func:
            cache_key = cache_key_func(config_id)
            self.cache_manager.set_json(cache_key, config_data, expiry=self.cache_ttl)
            logger.info(f'Cached {config_type} {config_id}')

    async def get_all_agent_configs(self, agent_id: UUID) -> Dict[str, Any]:
        """
        Fetch voice agent and all related configs from cache, with API fallback

        Strategy:
        1. Try fetching voice agent from cache
        2. If voice agent missing, fetch from floware API
        3. Try fetching all configs from cache
        4. For any missing configs, fetch them from floware API in parallel
        5. Cache the newly fetched configs for future requests
        6. If any API calls fail, raise HTTPException

        Args:
            agent_id: Voice agent UUID

        Returns:
            {
                'agent': {...},
                'llm_config': {...},
                'tts_config': {...},
                'stt_config': {...},
                'telephony_config': {...}
            }

        Raises:
            HTTPException: If agent not found or configs cannot be fetched
        """
        # Fetch voice agent from cache
        agent_key = get_voice_agent_cache_key(agent_id)
        agent = self.cache_manager.get_json(agent_key)

        # If agent not in cache, fetch from API
        if not agent:
            logger.info(f'Voice agent {agent_id} not found in cache, fetching from API')
            if not self.floware_http_client:
                logger.error(
                    f'Voice agent {agent_id} not found and no HTTP client configured'
                )
                raise HTTPException(
                    status_code=404, detail=f'Voice agent {agent_id} not found'
                )

            try:
                agent = await self.floware_http_client.fetch_voice_agent(agent_id)
                if not agent:
                    raise HTTPException(
                        status_code=404,
                        detail=f'Voice agent {agent_id} not found in floware API',
                    )
                # Cache the fetched agent
                self.cache_manager.set_json(agent_key, agent, expiry=self.cache_ttl)
                logger.info(f'Cached voice agent {agent_id} from API')
            except Exception as e:
                logger.error(f'Failed to fetch voice agent {agent_id} from API: {e}')
                raise HTTPException(
                    status_code=404, detail=f'Voice agent {agent_id} not found'
                )

        # Extract config IDs from agent
        llm_config_id = agent.get('llm_config_id')
        tts_config_id = agent.get('tts_config_id')
        stt_config_id = agent.get('stt_config_id')
        telephony_config_id = agent.get('telephony_config_id')

        if not all([llm_config_id, tts_config_id, stt_config_id]):
            logger.error(f'Voice agent {agent_id} missing required config IDs')
            raise HTTPException(
                status_code=500,
                detail=f'Voice agent {agent_id} has incomplete configuration',
            )

        # Try fetching all configs from cache first
        llm_config = self.cache_manager.get_json(
            get_llm_config_cache_key(llm_config_id)
        )
        tts_config = self.cache_manager.get_json(
            get_tts_config_cache_key(tts_config_id)
        )
        stt_config = self.cache_manager.get_json(
            get_stt_config_cache_key(stt_config_id)
        )
        telephony_config = self.cache_manager.get_json(
            get_telephony_config_cache_key(telephony_config_id)
        )

        # Identify missing configs
        missing_configs = []
        if not llm_config:
            missing_configs.append(('llm_inference_config', llm_config_id))
        if not tts_config:
            missing_configs.append(('tts_config', tts_config_id))
        if not stt_config:
            missing_configs.append(('stt_config', stt_config_id))
        if telephony_config_id and not telephony_config:
            missing_configs.append(('telephony_config', telephony_config_id))

        # If any configs are missing, fetch from API
        if missing_configs:
            logger.info(
                f'Missing {len(missing_configs)} configs for agent {agent_id}, '
                f'fetching from floware API: {missing_configs}'
            )

            # Fetch missing configs in parallel
            fetched_configs = await self._fetch_missing_configs_from_api(
                missing_configs
            )

            # Update local variables with fetched configs and cache them
            for config_type, config_id in missing_configs:
                config_data = fetched_configs[config_type]

                if config_type == 'llm_inference_config':
                    llm_config = config_data
                    self._cache_config(config_type, llm_config_id, config_data)
                elif config_type == 'tts_config':
                    tts_config = config_data
                    self._cache_config(config_type, tts_config_id, config_data)
                elif config_type == 'stt_config':
                    stt_config = config_data
                    self._cache_config(config_type, stt_config_id, config_data)
                elif config_type == 'telephony_config':
                    telephony_config = config_data
                    self._cache_config(config_type, telephony_config_id, config_data)

        # Final validation
        if not all([llm_config, tts_config, stt_config, telephony_config]):
            missing = []
            if not llm_config:
                missing.append(f'LLM config {llm_config_id}')
            if not tts_config:
                missing.append(f'TTS config {tts_config_id}')
            if not stt_config:
                missing.append(f'STT config {stt_config_id}')
            if not telephony_config:
                missing.append(f'Telephony config {telephony_config_id}')

            logger.error(f'Still missing configs after API fetch: {", ".join(missing)}')
            raise HTTPException(
                status_code=500,
                detail=f'Failed to fetch all required configs: {", ".join(missing)}',
            )

        logger.info(f'Successfully fetched all configs for voice agent {agent_id}')

        return {
            'agent': agent,
            'llm_config': llm_config,
            'tts_config': tts_config,
            'stt_config': stt_config,
            'telephony_config': telephony_config,
        }
