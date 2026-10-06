from dotenv import load_dotenv

# ruff: noqa: E402
load_dotenv()

from pathlib import Path

from dependency_injector import containers
from dependency_injector import providers

from common_module.runtime_settings import configure_runtime_settings
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.cache.redis_settings import RedisSettings
from rag_ingestion.service.index_status_publisher import IndexStatusPublisher
from flo_cloud.cloud_storage import CloudStorageManager
from flo_cloud.kms import FloKmsCipher
from flo_cloud.message_queue import MessageQueueManager
from flo_cloud._types import KmsKeySettings, QueueSettings
from rag_ingestion.processors.kb_storage_processor import KbStorageProcessor
from rag_ingestion.stream.rag_streamer import RagStreamListener

_CONFIG_INI = str(Path(__file__).resolve().parent / 'config.ini')


def _azure_queue_account_url(account_url: str | None) -> str | None:
    if not account_url:
        return None
    return account_url.replace('.blob.core.windows.net', '.queue.core.windows.net')


class RagIngestionContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=[_CONFIG_INI])

    redis_settings = providers.Factory(
        RedisSettings,
        host=config.redis.host,
        port=config.redis.port,
        protocol=config.redis.protocol,
        password=config.redis.password,
        db=config.redis.db,
        pool_size=config.redis.pool_size,
        pool_timeout=config.redis.pool_timeout,
    )

    # Worker-local Redis namespace for ingestion coordination.
    cache_manager = providers.Singleton(
        CacheManager,
        namespace='rag',
        settings=redis_settings,
    )

    # Index status events must land under floware's CacheManager namespace.
    floware_cache_manager = providers.Singleton(
        CacheManager,
        namespace=config.app_config.floware_app_name,
        settings=redis_settings,
    )


def main():
    container = RagIngestionContainer()
    config = container.config()

    cloud = config['cloud']
    storage = config['storage']
    queues = config['queues']
    kms_encryption = config['kms_encryption']
    app_config = config['app_config']
    env_config = config['env_config']
    model = config['model']

    configure_runtime_settings(
        floware_base_url=app_config['floware_service_url'] or 'http://localhost:8001',
        passthrough_secret=app_config['passthrough_secret'] or None,
        app_env=env_config['app_env'],
    )
    rag_target = queues['rag']
    if not rag_target:
        raise ValueError('queues.rag (RAG_QUEUE) must be set in config.ini')

    provider = cloud['provider']
    queue_settings = QueueSettings(
        provider=provider,
        target=rag_target,
        subscription=queues['rag_subscription'] or None,
        project_id=cloud['project_id'] or None,
        account_url=_azure_queue_account_url(storage['account_url'] or None),
    )
    event_manager = MessageQueueManager(queue_settings)
    storage_manager = CloudStorageManager(
        provider,
        account_url=storage['account_url'] or None,
        region_name=cloud['region'] or None,
    )

    index_status_publisher = IndexStatusPublisher(
        cache_manager=container.floware_cache_manager()
    )

    kms_cipher = None
    encryption_key = kms_encryption['key']
    if encryption_key:
        kms_cipher = FloKmsCipher(
            KmsKeySettings(
                provider=provider,
                key=encryption_key,
                key_version=kms_encryption['key_version'] or None,
                key_ring=kms_encryption['key_ring'] or None,
                project_id=cloud['project_id'] or None,
                location=cloud['location'] or None,
                region=cloud['region'] or None,
                key_vault_url=kms_encryption['key_vault_url'] or None,
            )
        )

    listener = RagStreamListener(
        streaming_batch_size=int(app_config['streaming_batch_size']),
        event_manager=event_manager,
        processor=KbStorageProcessor(
            storage_manager=storage_manager,
            kms_cipher=kms_cipher,
            index_status_publisher=index_status_publisher,
            inference_service_url=model['inference_service_url'],
            text_embedding_batch_size=model['text_embedding_batch_size'],
            image_embedding_batch_size=model['image_embedding_batch_size'],
        ),
        cache_manager=container.cache_manager(),
        retry_count=int(app_config['retry_count']),
    )

    listener.run_workers(thread_count=2)


if __name__ == '__main__':
    main()
