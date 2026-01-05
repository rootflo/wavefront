from rag_ingestion.stream.rag_streamer import RagStreamListener
from rag_ingestion.processors.kb_storage_processor import KbStorageProcessor
from db_repo_module.cache.cache_manager import CacheManager
from flo_cloud.kms import FloKmsService
from rag_ingestion.env import CLOUD_PROVIDER, RETRY_COUNT
from flo_cloud.cloud_storage import CloudStorageManager
from flo_cloud.message_queue import MessageQueueManager
import os


def main():
    # Original main logic for running workers
    event_manager = MessageQueueManager(CLOUD_PROVIDER)
    storage_manager = CloudStorageManager(CLOUD_PROVIDER)
    cache_manager = CacheManager(namespace='rag')
    encryption_service = None
    if (
        (CLOUD_PROVIDER == 'aws' and os.getenv('AWS_KMS_ARN') is not None)
        or CLOUD_PROVIDER == 'gcp'
        and (
            os.getenv('GCP_KMS_KEY_RING') is not None
            and os.getenv('GCP_KMS_CRYPTO_KEY') is not None
        )
    ):
        encryption_service = FloKmsService(cloud_provider=CLOUD_PROVIDER)

    # Initialize stream listener
    listener = RagStreamListener(
        event_manager=event_manager,
        processor=KbStorageProcessor(
            storage_manager,
            encryption_service,
        ),
        cache_manager=cache_manager,
        retry_count=RETRY_COUNT,
    )

    listener.run_workers(thread_count=2)


if __name__ == '__main__':
    main()
