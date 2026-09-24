from common_module.response_formatter import ResponseFormatter
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
    config = providers.Configuration(ini_files=['./config.ini'])

    response_formatter = providers.Singleton(ResponseFormatter)

    cache_manager = providers.Dependency()

    cloud_storage_manager = providers.Singleton(
        CloudStorageManager,
        provider=config.cloud.provider,
        account_url=config.azure.account_url,
        client_id=config.azure.client_id,
        client_secret=config.azure.client_secret,
        tenant_id=config.azure.tenant_id,
        region_name=config.cloud.region,
    )

    kms_signing_settings = providers.Factory(
        KmsKeySettings,
        provider=config.cloud.provider,
        key=config.kms_signing.key,
        key_version=config.kms_signing.key_version,
        key_ring=config.kms_signing.key_ring,
        project_id=config.cloud.project_id,
        location=config.cloud.location,
        region=config.cloud.region,
        vault_url=config.azure.key_vault_url,
        client_id=config.azure.client_id,
        client_secret=config.azure.client_secret,
        tenant_id=config.azure.tenant_id,
    )

    kms_encryption_settings = providers.Factory(
        KmsKeySettings,
        provider=config.cloud.provider,
        key=config.kms_encryption.key,
        key_version=config.kms_encryption.key_version,
        key_ring=config.kms_encryption.key_ring,
        project_id=config.cloud.project_id,
        location=config.cloud.location,
        region=config.cloud.region,
        vault_url=config.azure.key_vault_url,
        client_id=config.azure.client_id,
        client_secret=config.azure.client_secret,
        tenant_id=config.azure.tenant_id,
    )

    kms_signer = providers.Singleton(FloKmsSigner, settings=kms_signing_settings)
    kms_cipher = providers.Singleton(FloKmsCipher, settings=kms_encryption_settings)

    rag_queue_settings = providers.Factory(
        QueueSettings,
        provider=config.cloud.provider,
        target=config.queues.rag,
        subscription=config.queues.rag_subscription,
        project_id=config.cloud.project_id,
        account_url=providers.Callable(
            _azure_queue_account_url, config.azure.account_url
        ),
    )

    workflow_queue_settings = providers.Factory(
        QueueSettings,
        provider=config.cloud.provider,
        target=config.queues.workflow_worker,
        subscription=config.queues.workflow_subscription,
        project_id=config.cloud.project_id,
        account_url=providers.Callable(
            _azure_queue_account_url, config.azure.account_url
        ),
    )

    gold_queue_settings = providers.Factory(
        QueueSettings,
        provider=config.cloud.provider,
        target=config.queues.gold,
        subscription=None,
        project_id=config.cloud.project_id,
        account_url=providers.Callable(
            _azure_queue_account_url, config.azure.account_url
        ),
    )

    rag_queue = providers.Singleton(MessageQueueManager, settings=rag_queue_settings)
    workflow_queue = providers.Singleton(
        MessageQueueManager, settings=workflow_queue_settings
    )
    gold_queue = providers.Singleton(MessageQueueManager, settings=gold_queue_settings)
