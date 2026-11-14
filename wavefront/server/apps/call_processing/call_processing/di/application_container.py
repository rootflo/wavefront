from pathlib import Path

from dependency_injector import containers
from dependency_injector import providers

from call_processing.app_settings import CallProcessingAppSettings
from call_processing.cache.cache_manager import CacheManager
from call_processing.log.logger import configure_logging
from call_processing.services.common.context.store import (
    CallContextStore,
    create_context_redis,
)
from call_processing.services.common.voice_agent_cache_service import (
    VoiceAgentCacheService,
)
from call_processing.services.common.floware_http_client import FlowareHttpClient
from call_processing.services.telephony.session_service import TelephonySessionService
from call_processing.services.webrtc.room_service import WebRTCRoomService
from call_processing.services.webrtc.session_service import WebRTCSessionService
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
        pool_size=config.redis.pool_size,
        pool_timeout=config.redis.pool_timeout,
    )

    # Per-call tool results (async, fail-fast; CacheManager retries for seconds)
    call_context_redis = providers.Singleton(
        create_context_redis,
        host=config.redis.host,
        port=config.redis.port,
        protocol=config.redis.protocol,
        password=config.redis.password,
        db=config.redis.db,
        pool_size=config.redis.pool_size,
    )
    call_context_store = providers.Singleton(CallContextStore, redis=call_context_redis)

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

    # Phone call media streams
    telephony_session_service = providers.Singleton(
        TelephonySessionService,
        voice_agent_cache_service=voice_agent_cache_service,
        app_settings=app_settings,
        call_context_store=call_context_store,
    )

    # Browser (WebRTC) rooms + sessions
    webrtc_room_service = providers.Singleton(
        WebRTCRoomService,
        cache_manager=cache_manager,
        room_ttl_secs=app_settings.provided.webrtc.room_ttl_secs,
        max_session_secs=app_settings.provided.webrtc.max_session_secs,
    )

    webrtc_session_service = providers.Singleton(
        WebRTCSessionService,
        room_service=webrtc_room_service,
        voice_agent_cache_service=voice_agent_cache_service,
        app_settings=app_settings,
    )


def create_container() -> ApplicationContainer:
    container = ApplicationContainer()
    load_ini(container.config, CONFIG_INI)
    container.init_resources()
    return container
