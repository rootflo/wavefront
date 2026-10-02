from dependency_injector import containers
from dependency_injector import providers
from inference_app.env import (
    RATE_LIMIT_REQUESTS_PER_MINUTE,
    RATE_LIMIT_REQUESTS_PER_SECOND,
)
from inference_app.rate_limiter import SlidingWindowRateLimiter
from inference_app.service.image_embedding import ImageEmbedding
from inference_app.service.text_embedding import TextEmbeddingProvider


class InferenceAppContainer(containers.DeclarativeContainer):
    """DI container for inference_app.

    image_embedding is declared here as a Singleton placeholder.
    At startup (server.py lifespan) it is overridden with the actual
    clip_model_dir / dino_model_dir paths returned by sync_embedding_models().
    """

    config = providers.Configuration(ini_files=['config.ini'])

    image_embedding = providers.Singleton(ImageEmbedding)

    # Optional BGE-M3 model; loaded in the background from the lifespan when
    # BGE_M3_MODEL_URI is set, unavailable (503) otherwise.
    text_embedding_provider = providers.Singleton(TextEmbeddingProvider)

    rate_limiter = providers.Singleton(
        SlidingWindowRateLimiter,
        limits=[
            (RATE_LIMIT_REQUESTS_PER_SECOND, 1.0),
            (RATE_LIMIT_REQUESTS_PER_MINUTE, 60.0),
        ],
    )
