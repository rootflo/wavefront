from contextlib import asynccontextmanager
import glob
import os
from typing import Any, cast

from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from common_module.middleware.request_id_middleware import RequestIdMiddleware
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from starlette.middleware import _MiddlewareFactory

from floconsole.authorization.require_auth import RequireAuthMiddleware
from floconsole.di.application_container import ApplicationContainer
from floconsole.controllers.app_controller import app_router
from floconsole.controllers.app_user_controller import app_user_router
from floconsole.controllers.auth_controller import auth_router
from floconsole.controllers.floware_proxy_controller import floware_proxy_router
from floconsole.controllers.user_controller import user_router
from floconsole.db import DatabaseClient

load_dotenv()

# Initialize containers
common_container = CommonContainer(cache_manager=None)
application_container = ApplicationContainer(common_container=common_container)

# Wire containers
application_container.wire(
    modules=[__name__],
    packages=[
        'floconsole.controllers',
    ],
)

common_container.wire(
    modules=[__name__],
    packages=[
        'floconsole.controllers',
    ],
)


def _middleware(cls: type[Any]) -> _MiddlewareFactory[Any]:
    return cast(_MiddlewareFactory[Any], cls)


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
)

origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173')
allowed_origins = origins.split(',')

app.add_middleware(_middleware(RequestIdMiddleware))
app.add_middleware(_middleware(RequireAuthMiddleware))

# Configure CORS with proper security settings
app.add_middleware(
    _middleware(CORSMiddleware),
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
app.include_router(auth_router, prefix='/floconsole')
app.include_router(floware_proxy_router, prefix='/floconsole')
app.include_router(user_router, prefix='/floconsole')
app.include_router(app_router, prefix='/floconsole')
app.include_router(app_user_router, prefix='/floconsole')


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

# Running with Uvicorn (for local development)
if __name__ == '__main__':
    print(f'Starting application in environment: {environment}')
    if environment == 'production':
        uvicorn.run(
            'server:app', host='0.0.0.0', port=8002, workers=1, log_level='critical'
        )
        print(f'Started application in environment: {environment}')

    else:
        dirs = glob.glob('../../..//**/*_module/**', recursive=True)
        dirs.extend(glob.glob('../../..//**/plugins/**', recursive=True))
        dirs.extend(glob.glob('../../..//**/packages/**', recursive=True))
        dirs.append('../../floconsole')

        uvicorn.run(
            'server:app',
            host='0.0.0.0',
            port=8002,
            workers=1,
            reload=True,
            reload_includes=dirs,
            log_level='info',
        )
        print(f'Started application in environment: {environment}')
