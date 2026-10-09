from common_module.call_processing_cache import CallProcessingCacheInvalidator
from common_module.feature.feature_flag import FeatureFlags
from common_module.response_formatter import ResponseFormatter
from common_module.runtime_settings import RuntimeSettings
from dependency_injector import containers
from dependency_injector import providers

from flo_cloud.cloud_storage import CloudStorageManager
from flo_cloud.kms import FloKmsCipher, FloKmsSigner
from flo_cloud.message_queue import MessageQueueManager
from flo_cloud._types import KmsKeySettings, QueueSettings


def _azure_queue_account_url(account_url: str | None) -> str | None:
    if not account_url:
        return None
    return account_url.replace('.blob.core.windows.net', '.queue.core.windows.net')


class CommonContainer(containers.DeclarativeContainer):
    config = providers.Configuration()

    response_formatter = providers.Singleton(ResponseFormatter)

    runtime_settings = providers.Singleton(RuntimeSettings.from_config, config=config)

    feature_flags = providers.Singleton(FeatureFlags.from_config, config)

    call_processing_cache_invalidator = providers.Singleton(
        CallProcessingCacheInvalidator,
        call_processing_base_url=runtime_settings.provided.call_processing_base_url,
        passthrough_secret=runtime_settings.provided.passthrough_secret,
    )

    cache_manager = providers.Dependency()

    cloud_storage_manager = providers.Singleton(
        CloudStorageManager,
        provider=config.cloud.platform,
        region_name=config.cloud.region,
        account_url=config.storage.account_url,
    )

    kms_signing_settings = providers.Factory(
        KmsKeySettings,
        provider=config.cloud.platform,
        key=config.kms_signing.key,
        key_version=config.kms_signing.key_version,
        key_ring=config.kms_signing.key_ring,
        project_id=config.cloud.project_id,
        region=config.cloud.region,
        key_vault_url=config.kms_signing.key_vault_url,
    )

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

    kms_signer = providers.Singleton(FloKmsSigner, settings=kms_signing_settings)
    kms_cipher = providers.Singleton(FloKmsCipher, settings=kms_encryption_settings)

    rag_queue_settings = providers.Factory(
        QueueSettings,
        provider=config.cloud.platform,
        target=config.queues.rag,
        subscription=config.queues.rag_subscription,
        project_id=config.cloud.project_id,
        account_url=providers.Callable(
            _azure_queue_account_url, config.storage.account_url
        ),
    )

    gold_queue_settings = providers.Factory(
        QueueSettings,
        provider=config.cloud.platform,
        target=config.queues.gold,
        subscription=None,
        project_id=config.cloud.project_id,
        account_url=providers.Callable(
            _azure_queue_account_url, config.storage.account_url
        ),
    )

    rag_queue = providers.Singleton(MessageQueueManager, settings=rag_queue_settings)
    gold_queue = providers.Singleton(MessageQueueManager, settings=gold_queue_settings)
