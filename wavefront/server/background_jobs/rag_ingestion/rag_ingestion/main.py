from dotenv import load_dotenv

# ruff: noqa: E402
load_dotenv()

from dependency_injector import containers
from dependency_injector import providers

from common_module.runtime_settings import configure_runtime_settings
from db_repo_module.cache.cache_manager import CacheManager
from flo_cloud.cloud_storage import CloudStorageManager
from flo_cloud.kms import FloKmsCipher
from flo_cloud.message_queue import MessageQueueManager
from flo_cloud._types import KmsKeySettings, QueueSettings
from rag_ingestion.processors.kb_storage_processor import KbStorageProcessor
from rag_ingestion.stream.rag_streamer import RagStreamListener


def _azure_queue_account_url(account_url: str | None) -> str | None:
    if not account_url:
        return None
    return account_url.replace('.blob.core.windows.net', '.queue.core.windows.net')


class RagIngestionContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])


def main():
    container = RagIngestionContainer()
    config = container.config()

    cloud = config.get('cloud') or {}
    queues = config.get('queues') or {}
    azure = config.get('azure') or {}
    redis = config.get('redis') or {}
    kms_encryption = config.get('kms_encryption') or {}
    app_config = config.get('app_config') or {}
    env_config = config.get('env_config') or {}

    configure_runtime_settings(
        floware_base_url=app_config.get('floware_service_url')
        or 'http://localhost:8001',
        passthrough_secret=app_config.get('passthrough_secret') or None,
        app_env=env_config.get('app_env') or app_config.get('app_env') or 'dev',
    )
    rag_target = queues.get('rag')
    if not rag_target:
        raise ValueError('queues.rag (RAG_QUEUE) must be set in config.ini')

    provider = cloud.get('provider') or 'gcp'
    queue_settings = QueueSettings(
        provider=provider,
        target=rag_target,
        subscription=queues.get('rag_subscription') or None,
        project_id=cloud.get('project_id') or None,
        account_url=_azure_queue_account_url(azure.get('account_url') or None),
    )
    event_manager = MessageQueueManager(queue_settings)
    storage_manager = CloudStorageManager(
        provider,
        account_url=azure.get('account_url') or None,
        client_id=azure.get('client_id') or None,
        client_secret=azure.get('client_secret') or None,
        tenant_id=azure.get('tenant_id') or None,
        region_name=cloud.get('region') or None,
    )
    cache_manager = CacheManager(
        namespace='rag',
        host=redis.get('host') or 'localhost',
        port=redis.get('port') or 6379,
        protocol=redis.get('protocol') or 'redis',
        password=redis.get('password') or None,
        db=redis.get('db') or 0,
    )

    kms_cipher = None
    encryption_key = kms_encryption.get('key')
    if encryption_key:
        kms_cipher = FloKmsCipher(
            KmsKeySettings(
                provider=provider,
                key=encryption_key,
                key_version=kms_encryption.get('key_version') or None,
                key_ring=kms_encryption.get('key_ring') or None,
                project_id=cloud.get('project_id') or None,
                location=cloud.get('location') or None,
                region=cloud.get('region') or None,
                vault_url=azure.get('key_vault_url') or None,
                client_id=azure.get('client_id') or None,
                client_secret=azure.get('client_secret') or None,
                tenant_id=azure.get('tenant_id') or None,
            )
        )

    listener = RagStreamListener(
        streaming_batch_size=int(app_config.get('streaming_batch_size') or 100),
        event_manager=event_manager,
        processor=KbStorageProcessor(
            storage_manager,
            kms_cipher,
        ),
        cache_manager=cache_manager,
        retry_count=int(app_config.get('retry_count') or 3),
    )

    listener.run_workers(thread_count=2)


if __name__ == '__main__':
    main()
