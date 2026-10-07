from dependency_injector import containers
from dependency_injector import providers

from call_processing.cache.cache_manager import CacheManager
from call_processing.services.voice_agent_cache_service import VoiceAgentCacheService
from call_processing.services.floware_http_client import FlowareHttpClient


class ApplicationContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['./config.ini'])

    # Cache
    cache_manager = providers.Singleton(
        CacheManager,
        namespace=config.env_config.app_name,
        redis_host=config.redis.host,
        redis_port=config.redis.port,
        redis_protocol=config.redis.protocol,
        redis_password=config.redis.password,
        redis_db=config.redis.db,
        redis_username=config.redis.username,
        cloud_provider=config.cloud.platform,
        pool_size=config.redis.pool_size,
        pool_timeout=config.redis.pool_timeout,
    )

    # HTTP Client for floware
    floware_http_client = providers.Singleton(
        FlowareHttpClient,
        base_url=config.env_config.floware_base_url,
        passthrough_secret=config.env_config.passthrough_secret,
        app_env=config.env_config.app_env,
        timeout=30.0,
    )

    # Services
    voice_agent_cache_service = providers.Singleton(
        VoiceAgentCacheService,
        cache_manager=cache_manager,
        floware_http_client=floware_http_client,
    )
