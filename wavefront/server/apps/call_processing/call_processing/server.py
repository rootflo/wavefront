import glob

from call_processing.log.logger import logger
from common_module.runtime_settings import configure_runtime_settings
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn

from call_processing.di.application_container import ApplicationContainer
from call_processing.middleware import add_middlewares
from call_processing.router import include_routers

load_dotenv()

# Initialize containers
application_container = ApplicationContainer()
config = application_container.config()
env_config = config.get('env_config') or {}
web = config.get('web') or {}
environment = env_config.get('app_env') or 'production'
# Shared SecurityHeadersMiddleware still reads runtime_settings.app_env.
configure_runtime_settings(app_env=environment)

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
origins = str(web.get('allowed_origins') or 'http://localhost:8001')
add_middlewares(app, origins.split(','))
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
    print(f'Starting application in environment: {environment}')
    if environment == 'production':
        uvicorn.run(
            'server:app', host='0.0.0.0', port=8004, workers=1, log_level='critical'
        )
        print(f'Started application in environment: {environment}')

    else:
        dirs = glob.glob('../../..//**/*_module/**', recursive=True)
        dirs.extend(glob.glob('../../..//**/plugins/**', recursive=True))
        dirs.extend(glob.glob('../../..//**/packages/**', recursive=True))
        dirs.append('../../call_processing')

        uvicorn.run(
            'server:app',
            host='0.0.0.0',
            port=8004,
            workers=1,
            reload=True,
            reload_includes=dirs,
            log_level='info',
        )
        print(f'Started application in environment: {environment}')
