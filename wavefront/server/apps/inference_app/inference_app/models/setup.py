"""Load embedding models into the application container at process startup."""

from dependency_injector import providers

from common_module.log.logger import logger
from inference_app.di.application_container import ApplicationContainer
from inference_app.models.mock import use_mock_models
from inference_app.models.model_sync import (
    sync_embedding_models,
    sync_text_embedding_model,
)


def start_models(container: ApplicationContainer) -> None:
    """Sync/preload embeddings (or mocks) using ``container.config``."""
    config = container.config()
    if use_mock_models(config['models']['mock_models']):
        start_mock_models(container)
    else:
        start_real_models(container)


def start_mock_models(container: ApplicationContainer) -> None:
    from inference_app.service.mock_embeddings import (
        MockImageEmbedding,
        MockTextEmbedding,
    )

    logger.warning(
        'INFERENCE MOCK MODE: serving synthetic embeddings (no torch, or '
        'models.mock_models=true). For integration testing only; search '
        'results are not meaningful.'
    )
    container.image_embedding.override(providers.Singleton(MockImageEmbedding))
    container.text_embedding_provider().load(MockTextEmbedding)


def start_real_models(container: ApplicationContainer) -> None:
    # Imported here: these need torch, which mock mode runs without
    from inference_app.service.image_embedding import ImageEmbedding

    models = container.config()['models']
    cloud_provider = container.config()['cloud']['platform']

    logger.info('Syncing embedding models from cloud storage...')
    clip_dir, dino_dir = sync_embedding_models(
        clip_uri=models['clip_vit_base_patch32_uri'],
        dino_uri=models['dinov3_vitl16_uri'],
        cache_dir=models['cache_dir'],
        cloud_provider=cloud_provider,
    )
    logger.info('Cloud sync complete. Preloading ML models...')
    container.image_embedding.override(
        providers.Singleton(
            ImageEmbedding, clip_model_dir=clip_dir, dino_model_dir=dino_dir
        )
    )
    container.image_embedding()
    logger.info('ML models loaded and ready.')
    start_text_embedding_model(container)


def load_text_embedding_model(container: ApplicationContainer):
    from inference_app.service.text_embedding import TextEmbedding

    config = container.config()
    models = config['models']
    return TextEmbedding(
        sync_text_embedding_model(
            bge_m3_uri=models['bge_m3_uri'],
            cache_dir=models['cache_dir'],
            cloud_provider=config['cloud']['platform'],
        ),
        max_length=int(config['inference']['max_text_embedding_tokens']),
    )


def start_text_embedding_model(container: ApplicationContainer) -> None:
    """BGE-M3 is optional: start it loading in the background if configured,
    without holding up startup or failing it."""
    bge_m3_uri = container.config()['models']['bge_m3_uri']
    if not bge_m3_uri:
        logger.info('models.bge_m3_uri not set; text embeddings disabled.')
        return
    logger.info('Loading BGE-M3 text embedding model in the background...')
    container.text_embedding_provider().start_loading(
        lambda: load_text_embedding_model(container)
    )
