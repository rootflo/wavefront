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
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse

from inference_app.inference_app_container import InferenceAppContainer
from inference_app.controllers.inference_controller import inference_app_router
from inference_app.model_sync import sync_embedding_models
from inference_app.service.image_embedding import ImageEmbedding

# Initialize dependency containers
common_container = CommonContainer(cache_manager=None)
inference_app_container = InferenceAppContainer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('Syncing embedding models from cloud storage...')
    clip_dir, dino_dir = sync_embedding_models()
    logger.info('Cloud sync complete. Preloading ML models...')
    inference_app_container.image_embedding.override(
        providers.Singleton(ImageEmbedding, clip_model_dir=clip_dir, dino_model_dir=dino_dir)
    )
    inference_app_container.image_embedding()
    logger.info('ML models loaded and ready.')
    yield


app = FastAPI(
    title='FloConsole API',
    description='Console application for RootFlo platform',
    version='1.0.0',
    lifespan=lifespan,
)


origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173')
allowed_origins = origins.split(',')

app.add_middleware(RequestIdMiddleware)
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
    return JSONResponse(content={'status': 'ok'}, status_code=200)


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


environment = os.getenv('APP_ENV', 'dev')


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
