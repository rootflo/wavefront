from dependency_injector import containers
from dependency_injector import providers
from inference_app.service.image_analyser import ImageClarityService
from flo_cloud.cloud_storage import CloudStorageManager
from inference_app.service.model_repository import ModelRepository
from inference_app.service.model_inference import ModelInferenceService
from inference_app.service.image_embedding import ImageEmbedding


class InferenceAppContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])
    cache_manager = providers.Dependency()

    cloud_storage_manager = providers.Singleton(
        CloudStorageManager, provider=config.cloud_config.cloud_provider
    )

    model_repository = providers.Singleton(
        ModelRepository,
        cloud_storage_manager=cloud_storage_manager,
    )

    model_inference = providers.Singleton(ModelInferenceService)

    image_analyser = providers.Singleton(
        ImageClarityService,
    )

    image_embedding = providers.Singleton(
        ImageEmbedding,
    )
