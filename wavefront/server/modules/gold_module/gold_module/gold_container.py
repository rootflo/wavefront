from dependency_injector import containers
from dependency_injector import providers
from gold_module.services.image_service import ImageService


class GoldContainer(containers.DeclarativeContainer):
    config = providers.Configuration()

    cloud_storage_manager = providers.Dependency()
    gold_queue = providers.Dependency()

    image_service = providers.Singleton(
        ImageService,
        bucket_name=config.storage.application_bucket,
        cloud_storage_manager=cloud_storage_manager,
        message_queue=gold_queue,
    )
