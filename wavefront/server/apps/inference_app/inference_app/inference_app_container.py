from dependency_injector import containers
from dependency_injector import providers
from inference_app.service.image_embedding import ImageEmbedding


class InferenceAppContainer(containers.DeclarativeContainer):
    """DI container for inference_app.

    image_embedding is declared here as a Singleton placeholder.
    At startup (server.py lifespan) it is overridden with the actual
    clip_model_dir / dino_model_dir paths returned by sync_embedding_models().
    """

    config = providers.Configuration(ini_files=['config.ini'])

    image_embedding = providers.Singleton(ImageEmbedding)
