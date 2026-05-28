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
    get_tools_config_cache_key,
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
                            For 'tools', config_id is the agent_id

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
        tasks = []
        for config_type, config_id in missing_configs:
            if config_type == 'tools':
                # Tools are fetched by agent_id
                tasks.append(self.floware_http_client.get_agent_tools(config_id))
            else:
                # Other configs are fetched by config_id
                tasks.append(
                    self.floware_http_client.fetch_config(config_type, config_id)
                )

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
            'tools': get_tools_config_cache_key,
        }

        cache_key_func = cache_key_funcs.get(config_type)
        if cache_key_func:
            cache_key = cache_key_func(config_id)
            self.cache_manager.set_json(cache_key, config_data, expiry=self.cache_ttl)
            if config_type == 'tools':
                logger.info(
                    f'Cached {len(config_data) if config_data else 0} tools for agent {config_id}'
                )
            else:
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
                'telephony_config': {...},
                'tools': {...}
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

        # Try fetching tools from cache
        tools = self.cache_manager.get_json(get_tools_config_cache_key(agent_id))

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
        if tools is None:
            missing_configs.append(('tools', agent_id))

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
                elif config_type == 'tools':
                    tools = config_data
                    self._cache_config(config_type, agent_id, config_data)

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

        # Default tools to empty list if not fetched
        if tools is None:
            tools = []

        logger.info(f'Successfully fetched all configs for voice agent {agent_id}')

        return {
            'agent': agent,
            'llm_config': llm_config,
            'tts_config': tts_config,
            'stt_config': stt_config,
            'telephony_config': telephony_config,
            'tools': tools,
        }

    async def get_agent_by_inbound_number(
        self, phone_number: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get voice agent by inbound phone number (with caching).

        Strategy:
        1. Try cache first using inbound_number:{phone_number} key
        2. If cache miss, fetch from floware API
        3. Cache the agent ID mapping with 24-hour TTL
        4. Return full agent dict

        Args:
            phone_number: E.164 formatted phone number

        Returns:
            Voice agent dict or None if not found
        """
        cache_key = f'inbound_number:{phone_number}'

        # Try cache first
        cached_agent_id = self.cache_manager.get_str(cache_key)
        if cached_agent_id:
            logger.info(
                f'Cache hit for inbound number: {phone_number} -> agent {cached_agent_id}'
            )

            # Fetch agent from cache or API
            agent_key = get_voice_agent_cache_key(UUID(cached_agent_id))
            agent = self.cache_manager.get_json(agent_key)

            if agent:
                return agent
            else:
                # Agent not in cache, fetch from API
                if self.floware_http_client:
                    try:
                        agent = await self.floware_http_client.fetch_voice_agent(
                            UUID(cached_agent_id)
                        )
                        if agent:
                            # Cache the agent
                            self.cache_manager.set_json(
                                agent_key, agent, expiry=self.cache_ttl
                            )
                            return agent
                    except Exception as e:
                        logger.error(
                            f'Failed to fetch agent {cached_agent_id} from API: {e}'
                        )

        # Cache miss - fetch from floware API
        logger.info(f'Cache miss - fetching agent by inbound number: {phone_number}')

        if not self.floware_http_client:
            logger.error('No HTTP client configured for inbound number lookup')
            return None

        try:
            agent = await self.floware_http_client.get_agent_by_inbound_number(
                phone_number
            )

            if agent:
                agent_id = agent.get('id')
                # Cache the inbound number -> agent ID mapping
                self.cache_manager.add(cache_key, str(agent_id), expiry=self.cache_ttl)

                # Cache the agent itself
                agent_key = get_voice_agent_cache_key(UUID(agent_id))
                self.cache_manager.set_json(agent_key, agent, expiry=self.cache_ttl)

                logger.info(f'Cached inbound number {phone_number} -> agent {agent_id}')
                return agent
            else:
                logger.warning(f'No agent found for inbound number: {phone_number}')
                return None

        except Exception as e:
            logger.error(
                f'Failed to fetch agent by inbound number {phone_number}: {e}',
                exc_info=True,
            )
            return None

    async def get_welcome_message_audio_url(self, agent_id: str) -> str:
        """
        Get welcome message audio URL for an agent (with caching).

        Strategy:
        1. Try cache first using voice_agent_welcome_url:{agent_id} key
        2. If cache miss, fetch from floware API
        3. Cache the URL with ~2 hour TTL (same as floware)

        Args:
            agent_id: Voice agent UUID (string)

        Returns:
            Presigned URL for welcome message audio or empty string if not available
        """
        cache_key = f'voice_agent_welcome_url:{agent_id}'

        # Try cache first
        cached_url = self.cache_manager.get_str(cache_key)
        if cached_url:
            logger.info(f'Cache hit for welcome message URL: {agent_id}')
            return cached_url

        # Cache miss - fetch from floware API
        logger.info(f'Cache miss - fetching welcome message URL for agent: {agent_id}')

        if not self.floware_http_client:
            logger.error('No HTTP client configured for welcome message URL fetch')
            return ''

        try:
            url = await self.floware_http_client.get_welcome_message_audio_url(agent_id)

            if url:
                # Cache URL with ~2 hour TTL (7100 seconds - matches floware)
                self.cache_manager.add(cache_key, url, expiry=7100)
                logger.info(f'Cached welcome message URL for agent {agent_id}')
                return url
            else:
                logger.warning(f'No welcome message URL for agent: {agent_id}')
                return ''

        except Exception as e:
            logger.error(
                f'Failed to fetch welcome message URL for agent {agent_id}: {e}',
                exc_info=True,
            )
            return ''
