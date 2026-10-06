from pathlib import Path

from dependency_injector import containers
from dependency_injector import providers

from inference_app.middleware.rate_limiter import SlidingWindowRateLimiter
from inference_app.service.text_embedding_provider import TextEmbeddingProvider

# Package root (parent of di/), so config.ini resolves independent of CWD.
_CONFIG_INI = str(Path(__file__).resolve().parent.parent / 'config.ini')


def _image_embedding_not_configured():
    raise RuntimeError(
        'image_embedding is configured at startup (models.setup): the '
        'real models, or mock embeddings where torch is unavailable'
    )


def _rate_limit_windows(per_second: str | int, per_minute: str | int):
    return [
        (int(per_second), 1.0),
        (int(per_minute), 60.0),
    ]


class ApplicationContainer(containers.DeclarativeContainer):
    """DI container for inference_app.

    image_embedding is a placeholder overridden at startup (models.setup)
    with ImageEmbedding on the synced model directories, or with
    MockImageEmbedding in mock mode. It is not imported here, so the app can
    start without torch.
    """

    config = providers.Configuration(ini_files=[_CONFIG_INI])

    image_embedding = providers.Singleton(_image_embedding_not_configured)

    # Optional BGE-M3 model; loaded in the background from models.setup when
    # models.bge_m3_uri is set, unavailable (503) otherwise.
    text_embedding_provider = providers.Singleton(TextEmbeddingProvider)

    rate_limiter = providers.Singleton(
        SlidingWindowRateLimiter,
        limits=providers.Callable(
            _rate_limit_windows,
            config.inference.rate_limit_requests_per_second,
            config.inference.rate_limit_requests_per_minute,
        ),
    )
