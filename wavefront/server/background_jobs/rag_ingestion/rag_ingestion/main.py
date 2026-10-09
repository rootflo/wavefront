from flo_lib.http import alias_httpx

alias_httpx()
# ruff: noqa: E402
from dotenv import load_dotenv

load_dotenv()

from pathlib import Path

from common_module.common_container import CommonContainer
from common_module.config_loader import load_ini
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.cache.redis_settings import RedisSettings
from dependency_injector import containers
from dependency_injector import providers
from rag_ingestion.service.index_status_publisher import IndexStatusPublisher
from rag_ingestion.processors.kb_storage_processor import KbStorageProcessor
from rag_ingestion.stream.rag_streamer import RagStreamListener

CONFIG_INI = Path(__file__).resolve().parent / 'config.ini'


class ApplicationContainer(containers.DeclarativeContainer):
    config = providers.Configuration(strict=True)

    common = providers.Container(
        CommonContainer,
        config=config,
        cache_manager=providers.Object(None),
    )

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


def create_container() -> ApplicationContainer:
    container = ApplicationContainer()
    load_ini(container.config, CONFIG_INI)
    return container


def main():
    container = create_container()
    config = container.config()
    runtime = container.common.runtime_settings()

    app_config = config['app_config']
    model = config['model']

    if not config['queues']['rag']:
        raise ValueError('queues.rag (RAG_QUEUE) must be set in config.ini')

    # Only build the cipher when a key is configured; floware may upload
    # documents unencrypted (localstack / some deploys).
    encryption_key = config['kms_encryption']['key']
    kms_cipher = container.common.kms_cipher() if encryption_key else None

    listener = RagStreamListener(
        streaming_batch_size=int(app_config['streaming_batch_size']),
        event_manager=container.common.rag_queue(),
        processor=KbStorageProcessor(
            storage_manager=container.common.cloud_storage_manager(),
            kms_cipher=kms_cipher,
            index_status_publisher=IndexStatusPublisher(
                cache_manager=container.floware_cache_manager()
            ),
            inference_service_url=model['inference_service_url'],
            runtime_settings=runtime,
            text_embedding_batch_size=model['text_embedding_batch_size'],
            image_embedding_batch_size=model['image_embedding_batch_size'],
        ),
        cache_manager=container.cache_manager(),
        retry_count=int(app_config['retry_count']),
    )

    listener.run_workers(thread_count=2)


if __name__ == '__main__':
    main()
