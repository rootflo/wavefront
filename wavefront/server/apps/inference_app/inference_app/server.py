import glob
import os
from contextlib import asynccontextmanager
from dependency_injector import providers

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ruff: noqa: E402
load_dotenv()

from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from common_module.middleware.request_id_middleware import RequestIdMiddleware
from common_module.middleware.security_headers import SecurityHeadersMiddleware
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse

from inference_app.inference_app_container import InferenceAppContainer
from inference_app.controllers.inference_controller import inference_app_router
from inference_app.env import BGE_M3_MODEL_URI, MAX_TEXT_EMBEDDING_TOKENS
from inference_app.mock import use_mock_models
from inference_app.model_sync import sync_embedding_models, sync_text_embedding_model

# Initialize dependency containers
common_container = CommonContainer(cache_manager=None)
inference_app_container = InferenceAppContainer()


# Mock embeddings where the real models can't run (no torch: Intel Macs), or
# when INFERENCE_MOCK_MODELS=true. Decided once, at startup.
MOCK_MODELS = use_mock_models()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if MOCK_MODELS:
        start_mock_models()
    else:
        start_real_models()
    yield


def start_mock_models() -> None:
    from inference_app.service.mock_embeddings import (
        MockImageEmbedding,
        MockTextEmbedding,
    )

    logger.warning(
        'INFERENCE MOCK MODE: serving synthetic embeddings (no torch, or '
        'INFERENCE_MOCK_MODELS=true). For integration testing only; search '
        'results are not meaningful.'
    )
    inference_app_container.image_embedding.override(
        providers.Singleton(MockImageEmbedding)
    )
    inference_app_container.text_embedding_provider().load(MockTextEmbedding)


def start_real_models() -> None:
    # Imported here: these need torch, which mock mode runs without
    from inference_app.service.image_embedding import ImageEmbedding

    logger.info('Syncing embedding models from cloud storage...')
    clip_dir, dino_dir = sync_embedding_models()
    logger.info('Cloud sync complete. Preloading ML models...')
    inference_app_container.image_embedding.override(
        providers.Singleton(
            ImageEmbedding, clip_model_dir=clip_dir, dino_model_dir=dino_dir
        )
    )
    inference_app_container.image_embedding()
    logger.info('ML models loaded and ready.')
    start_text_embedding_model()


def load_text_embedding_model():
    from inference_app.service.text_embedding import TextEmbedding

    return TextEmbedding(
        sync_text_embedding_model(), max_length=MAX_TEXT_EMBEDDING_TOKENS
    )


def start_text_embedding_model() -> None:
    """BGE-M3 is optional: start it loading in the background if configured,
    without holding up startup or failing it."""
    if not BGE_M3_MODEL_URI:
        logger.info('BGE_M3_MODEL_URI not set; text embeddings disabled.')
        return
    logger.info('Loading BGE-M3 text embedding model in the background...')
    inference_app_container.text_embedding_provider().start_loading(
        load_text_embedding_model
    )


environment = os.getenv('APP_ENV', 'production')

# The interactive docs and the OpenAPI schema are off everywhere except dev,
# so a new/unknown APP_ENV value stays closed rather than exposing the surface.
is_dev = environment == 'dev'

app = FastAPI(
    title='FloConsole API',
    description='Console application for RootFlo platform',
    version='1.0.0',
    lifespan=lifespan,
    openapi_url='/openapi.json' if is_dev else None,
    docs_url='/docs' if is_dev else None,
    redoc_url='/redoc' if is_dev else None,
)


origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173')
allowed_origins = origins.split(',')

app.add_middleware(RequestIdMiddleware)
# Strict default-src 'none' CSP plus the rest of the security headers; /docs and
# /redoc get their own relaxed policy when APP_ENV=dev.
app.add_middleware(SecurityHeadersMiddleware)
# Configure CORS with proper security settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
    allow_headers=['*'],
    expose_headers=[
        'X-Content-Type-Options',
        'X-XSS-Protection',
        'X-Frame-Options',
        'Referrer-Policy',
        'Content-Security-Policy',
        'Pragma',
        'Expires',
        'Strict-Transport-Security',
        'Cache-Control',
    ],
)

# Include routers
app.include_router(inference_app_router, prefix='/inference')


@app.get('/inference/v1/health')
async def health_check():
    return JSONResponse(
        content={'status': 'ok', 'mock_models': MOCK_MODELS}, status_code=200
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Skip HTTPExceptions (they're handled by FastAPI)
    if isinstance(exc, HTTPException):
        raise exc

    error_message = 'An unexpected error has occurred while performing this action, please try again'
    if environment != 'production':
        error_message += f' - {str(exc)}'

    logger.error(f'Error in API call: {exc}', exc_info=True)

    exception_response_formatter = ResponseFormatter()
    return JSONResponse(
        status_code=500,
        content=exception_response_formatter.buildErrorResponse(error=error_message),
    )


common_container.wire(
    modules=[__name__],
    packages=['inference_app.controllers'],
)

inference_app_container.wire(
    modules=[__name__],
    packages=['inference_app.controllers'],
)


# Running with Uvicorn (for local development)
if __name__ == '__main__':
    print(f'Starting application in environment: {environment}')
    if environment == 'production':
        uvicorn.run(
            'server:app', host='0.0.0.0', port=8003, workers=1, log_level='critical'
        )
    else:
        dirs = glob.glob('apps/inference-app/inference_app/**/*.py', recursive=True)

        uvicorn.run(
            'server:app',
            host='0.0.0.0',
            port=8003,
            workers=1,
            reload=True,
            reload_includes=dirs,
            log_level='info',
        )
