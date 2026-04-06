from dependency_injector import containers
from dependency_injector import providers
from inference_app.service.image_embedding import ImageEmbedding


class InferenceAppContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])

    image_embedding = providers.Singleton(ImageEmbedding)
