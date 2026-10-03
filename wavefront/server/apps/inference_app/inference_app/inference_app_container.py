from dependency_injector import containers
from dependency_injector import providers
from inference_app.env import (
    RATE_LIMIT_REQUESTS_PER_MINUTE,
    RATE_LIMIT_REQUESTS_PER_SECOND,
)
from inference_app.rate_limiter import SlidingWindowRateLimiter
from inference_app.service.text_embedding_provider import TextEmbeddingProvider


def _image_embedding_not_configured():
    raise RuntimeError(
        'image_embedding is configured at startup (server.py lifespan): the '
        'real models, or mock embeddings where torch is unavailable'
    )


class InferenceAppContainer(containers.DeclarativeContainer):
    """DI container for inference_app.

    image_embedding is a placeholder overridden at startup (server.py
    lifespan) with ImageEmbedding on the synced model directories, or with
    MockImageEmbedding in mock mode. It is not imported here, so the app can
    start without torch.
    """

    config = providers.Configuration(ini_files=['config.ini'])

    image_embedding = providers.Singleton(_image_embedding_not_configured)

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
