from pathlib import Path

from dependency_injector import containers
from dependency_injector import providers

from call_processing.app_settings import CallProcessingAppSettings
from call_processing.cache.cache_manager import CacheManager
from call_processing.log.logger import configure_logging
from call_processing.services.voice_agent_cache_service import VoiceAgentCacheService
from call_processing.services.floware_http_client import FlowareHttpClient
from common_module.config_loader import load_ini

CONFIG_INI = Path(__file__).resolve().parent.parent / 'config.ini'


class ApplicationContainer(containers.DeclarativeContainer):
    config = providers.Configuration(strict=True)

    logging = providers.Resource(
        configure_logging, log_level=config.env_config.log_level
    )

    app_settings = providers.Singleton(CallProcessingAppSettings.from_config, config)

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


def create_container() -> ApplicationContainer:
    container = ApplicationContainer()
    load_ini(container.config, CONFIG_INI)
    container.init_resources()
    return container
