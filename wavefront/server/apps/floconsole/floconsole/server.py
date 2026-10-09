from contextlib import asynccontextmanager
import glob

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn

# ruff: noqa: E402
load_dotenv()  # Before di: create_container() reads config.ini with envs_required

from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from floconsole.db import DatabaseClient
from floconsole.di import application_container
from floconsole.middleware.setup import add_middlewares
from floconsole.router.setup import include_routers

runtime = application_container.common.runtime_settings()
environment = runtime.app_env

# The interactive docs and the OpenAPI schema are off everywhere except dev,
# so a new/unknown APP_ENV value stays closed rather than exposing the surface.
is_dev = environment == 'dev'

# Wire containers
application_container.wire(
    modules=[
        __name__,
        'floconsole.authorization.require_auth',
    ],
    packages=[
        'floconsole.controllers',
    ],
)

application_container.common.wire(
    modules=[
        __name__,
        'floconsole.authorization.require_auth',
    ],
    packages=[
        'floconsole.controllers',
    ],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup code
    logger.info('Starting FloConsole application...')

    # Initialize database connection
    db_client: DatabaseClient = application_container.db_client()

    if isinstance(db_client, DatabaseClient):
        await db_client.connect()
    else:
        raise TypeError('db_client is not an instance of DatabaseClient')

    # Run database migrations
    try:
        db_client.run_migration()
        logger.info('Database migrations completed successfully')
    except Exception as e:
        logger.error(f'Database migration failed: {e}')
        raise

    yield

    # Shutdown code
    logger.info('Shutting down FloConsole application...')

    # Close database connection
    try:
        await db_client.close()
        logger.info('Database connection closed')
    except Exception as e:
        logger.error(f'Error closing database connection: {e}')


app = FastAPI(
    title='FloConsole API',
    description='Console application for RootFlo platform',
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


# Running with Uvicorn (for local development)
if __name__ == '__main__':
    config = application_container.config()
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
        dirs.append('../../floconsole')

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
