import glob

from dotenv import load_dotenv

# ruff: noqa: E402
load_dotenv()

from call_processing.log.logger import configure_logging, logger
from common_module.runtime_settings import RuntimeSettings
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn

from call_processing.di.application_container import ApplicationContainer
from call_processing.app_settings import (
    CallProcessingAppSettings,
    configure_call_processing,
)
from call_processing.middleware import add_middlewares
from call_processing.router import include_routers

# Initialize containers
application_container = ApplicationContainer()
config = application_container.config()
configure_call_processing(CallProcessingAppSettings.from_config(config))
configure_logging(config['env_config']['log_level'])
runtime = RuntimeSettings.from_config(config)
environment = runtime.app_env

# Wire containers
application_container.wire(
    modules=[__name__],
    packages=[
        'call_processing.controllers',
    ],
)


# The interactive docs and the OpenAPI schema are off everywhere except dev,
# so a new/unknown APP_ENV value stays closed rather than exposing the surface.
is_dev = environment == 'dev'

app = FastAPI(
    title='Call Processing API',
    description='Real-time voice call processing with Pipecat',
    version='1.0.0',
    openapi_url='/openapi.json' if is_dev else None,
    docs_url='/docs' if is_dev else None,
    redoc_url='/redoc' if is_dev else None,
)

# Middlewares & Routers
add_middlewares(app, runtime.allowed_origins, runtime.app_env)
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

    return JSONResponse(
        status_code=500,
        content=error_message,
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
        print(f'Started application in environment: {environment}')

    else:
        dirs = glob.glob('../../..//**/*_module/**', recursive=True)
        dirs.extend(glob.glob('../../..//**/plugins/**', recursive=True))
        dirs.extend(glob.glob('../../..//**/packages/**', recursive=True))
        dirs.append('../../call_processing')

        uvicorn.run(
            'server:app',
            host=host,
            port=port,
            workers=1,
            reload=True,
            reload_includes=dirs,
            log_level=server['reload_log_level'],
        )
        print(f'Started application in environment: {environment}')
