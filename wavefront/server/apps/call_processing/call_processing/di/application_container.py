from pathlib import Path

from dependency_injector import containers
from dependency_injector import providers

from call_processing.app_settings import CallProcessingAppSettings
from call_processing.cache.cache_manager import CacheManager
from call_processing.log.logger import configure_logging
from call_processing.services.common.voice_agent_cache_service import (
    VoiceAgentCacheService,
)
from call_processing.services.common.floware_http_client import FlowareHttpClient
from call_processing.services.telephony.session_service import TelephonySessionService
from call_processing.services.webrtc.room_service import WebRTCRoomService
from call_processing.services.webrtc.session_service import WebRTCSessionService
from common_module.config_loader import load_ini
from common_module.feature.feature_flag import FeatureFlags
from common_module.security.secret_cipher import SecretCipher
from flo_cloud._types import KmsKeySettings
from flo_cloud.envelope import EnvelopeCipher
from flo_cloud.kms import FloKmsCipher

CONFIG_INI = Path(__file__).resolve().parent.parent / 'config.ini'


class ApplicationContainer(containers.DeclarativeContainer):
    config = providers.Configuration(strict=True)

    logging = providers.Resource(
        configure_logging, log_level=config.env_config.log_level
    )

    app_settings = providers.Singleton(CallProcessingAppSettings.from_config, config)

    feature_flags = providers.Singleton(FeatureFlags.from_config, config)

    # Secrets in floware's configs arrive encrypted when the flag is on
    kms_encryption_settings = providers.Factory(
        KmsKeySettings,
        provider=config.cloud.platform,
        key=config.kms_encryption.key,
        key_version=config.kms_encryption.key_version,
        key_ring=config.kms_encryption.key_ring,
        project_id=config.cloud.project_id,
        region=config.cloud.region,
        key_vault_url=config.kms_encryption.key_vault_url,
    )
    kms_cipher = providers.Singleton(FloKmsCipher, settings=kms_encryption_settings)

    # The factory is handed over uncalled, so KMS is only touched with the flag on.
    secret_cipher = providers.Singleton(
        SecretCipher,
        enabled=feature_flags.provided.envelope_encryption_enabled,
        envelope_factory=providers.Factory(
            EnvelopeCipher, kms_cipher=kms_cipher
        ).provider,
    )

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
        secret_cipher=secret_cipher,
    )

    # Phone call media streams
    telephony_session_service = providers.Singleton(
        TelephonySessionService,
        voice_agent_cache_service=voice_agent_cache_service,
        app_settings=app_settings,
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
