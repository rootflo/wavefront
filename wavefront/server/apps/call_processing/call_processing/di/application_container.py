from dependency_injector import containers
from dependency_injector import providers

from call_processing.cache.cache_manager import CacheManager
from call_processing.services.voice_agent_cache_service import VoiceAgentCacheService
from call_processing.services.floware_http_client import FlowareHttpClient


class ApplicationContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['./config.ini'])

    # Cache
    cache_manager = providers.Singleton(
        CacheManager, namespace=config.env_config.app_name
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
