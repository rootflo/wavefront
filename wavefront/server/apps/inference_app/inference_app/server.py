from flo_lib.http import alias_httpx

alias_httpx()

# ruff: noqa: E402
import glob
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn

# ruff: noqa: E402
load_dotenv()

from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter

from inference_app.di import application_container
from inference_app.middleware.setup import add_middlewares
from inference_app.models.setup import start_models
from inference_app.router.setup import include_routers

config = application_container.config()
runtime = application_container.common.runtime_settings()
environment = runtime.app_env


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_models(application_container)
    yield


# The interactive docs and the OpenAPI schema are off everywhere except dev,
# so a new/unknown APP_ENV value stays closed rather than exposing the surface.
is_dev = environment == 'dev'

app = FastAPI(
    title='Inference API',
    description='Embedding inference service for RootFlo platform',
    version='1.0.0',
    lifespan=lifespan,
    openapi_url='/openapi.json' if is_dev else None,
    docs_url='/docs' if is_dev else None,
    redoc_url='/redoc' if is_dev else None,
)

# Middlewares & Routers
add_middlewares(
    app, allowed_origins=runtime.allowed_origins, environment=runtime.app_env
)
include_routers(app)


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


application_container.common.wire(
    modules=[__name__],
    packages=['inference_app.controllers'],
)

application_container.wire(
    modules=[__name__],
    packages=['inference_app.controllers'],
)


# Running with Uvicorn (for local development)
if __name__ == '__main__':
    server = config['server']
    host = server['host']
    port = int(server['port'])
    print(f'Starting application in environment: {environment}')
    if environment == 'production':
        uvicorn.run(
            'server:app',
            host=host,
            port=port,
            workers=1,
            log_level=server['uvicorn_log_level'],
        )
    else:
        dirs = glob.glob('apps/inference-app/inference_app/**/*.py', recursive=True)

        uvicorn.run(
            'server:app',
            host=host,
            port=port,
            workers=1,
            reload=True,
            reload_includes=dirs,
            log_level=server['reload_log_level'],
        )
