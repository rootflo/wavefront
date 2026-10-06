from collections.abc import Mapping
from typing import Any

from dependency_injector import providers

from common_module.log.logger import logger
from inference_app.di.application_container import ApplicationContainer
from inference_app.models.mock import use_mock_models
from inference_app.models.model_sync import (
    sync_embedding_models,
    sync_text_embedding_model,
)

# Set by configure(); used by startup helpers and tests that monkeypatch them.
_container: ApplicationContainer | None = None
BGE_M3_MODEL_URI = ''
MAX_TEXT_EMBEDDING_TOKENS = 512
CLIP_VIT_BASE_PATCH32_MODEL_URI = ''
DINOV3_VITL16_HF_MODEL_URI = ''
MODEL_CACHE_DIR = '/tmp/model-cache'
CLOUD_PROVIDER = ''
MOCK_MODELS = False


def configure(
    container: ApplicationContainer,
    *,
    models: Mapping[str, Any],
    inference: Mapping[str, Any],
    cloud: Mapping[str, Any],
) -> None:
    global _container
    global BGE_M3_MODEL_URI, MAX_TEXT_EMBEDDING_TOKENS
    global CLIP_VIT_BASE_PATCH32_MODEL_URI, DINOV3_VITL16_HF_MODEL_URI
    global MODEL_CACHE_DIR, CLOUD_PROVIDER, MOCK_MODELS

    _container = container
    BGE_M3_MODEL_URI = models['bge_m3_uri']
    MAX_TEXT_EMBEDDING_TOKENS = int(inference['max_text_embedding_tokens'])
    CLIP_VIT_BASE_PATCH32_MODEL_URI = models['clip_vit_base_patch32_uri']
    DINOV3_VITL16_HF_MODEL_URI = models['dinov3_vitl16_uri']
    MODEL_CACHE_DIR = models['cache_dir']
    CLOUD_PROVIDER = cloud['provider']
    # Mock embeddings where the real models can't run (no torch: Intel Macs),
    # or when models.mock_models=true. Decided once, at configure time.
    MOCK_MODELS = use_mock_models(models['mock_models'])


def start_models() -> None:
    if MOCK_MODELS:
        start_mock_models()
    else:
        start_real_models()


def start_mock_models() -> None:
    from inference_app.service.mock_embeddings import (
        MockImageEmbedding,
        MockTextEmbedding,
    )

    logger.warning(
        'INFERENCE MOCK MODE: serving synthetic embeddings (no torch, or '
        'models.mock_models=true). For integration testing only; search '
        'results are not meaningful.'
    )
    container = _require_container()
    container.image_embedding.override(providers.Singleton(MockImageEmbedding))
    container.text_embedding_provider().load(MockTextEmbedding)


def start_real_models() -> None:
    # Imported here: these need torch, which mock mode runs without
    from inference_app.service.image_embedding import ImageEmbedding

    logger.info('Syncing embedding models from cloud storage...')
    clip_dir, dino_dir = sync_embedding_models(
        clip_uri=CLIP_VIT_BASE_PATCH32_MODEL_URI,
        dino_uri=DINOV3_VITL16_HF_MODEL_URI,
        cache_dir=MODEL_CACHE_DIR,
        cloud_provider=CLOUD_PROVIDER,
    )
    logger.info('Cloud sync complete. Preloading ML models...')
    container = _require_container()
    container.image_embedding.override(
        providers.Singleton(
            ImageEmbedding, clip_model_dir=clip_dir, dino_model_dir=dino_dir
        )
    )
    container.image_embedding()
    logger.info('ML models loaded and ready.')
    start_text_embedding_model()


def load_text_embedding_model():
    from inference_app.service.text_embedding import TextEmbedding

    return TextEmbedding(
        sync_text_embedding_model(
            bge_m3_uri=BGE_M3_MODEL_URI,
            cache_dir=MODEL_CACHE_DIR,
            cloud_provider=CLOUD_PROVIDER,
        ),
        max_length=MAX_TEXT_EMBEDDING_TOKENS,
    )


def start_text_embedding_model() -> None:
    """BGE-M3 is optional: start it loading in the background if configured,
    without holding up startup or failing it."""
    if not BGE_M3_MODEL_URI:
        logger.info('models.bge_m3_uri not set; text embeddings disabled.')
        return
    logger.info('Loading BGE-M3 text embedding model in the background...')
    _require_container().text_embedding_provider().start_loading(
        load_text_embedding_model
    )


def _require_container() -> ApplicationContainer:
    if _container is None:
        raise RuntimeError('models.setup.configure() must be called before startup')
    return _container
