import glob
import os

from call_processing.log.logger import logger
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from call_processing.di.application_container import ApplicationContainer
from call_processing.controllers.webhook_controller import webhook_router
from call_processing.controllers.cache_controller import cache_router

load_dotenv()

environment = os.getenv('APP_ENV', 'dev')

# Initialize containers
application_container = ApplicationContainer()

# Wire containers
application_container.wire(
    modules=[__name__],
    packages=[
        'call_processing.controllers',
    ],
)


app = FastAPI(
    title='Call Processing API',
    description='Real-time voice call processing with Pipecat',
    version='1.0.0',
)

origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:8001')
allowed_origins = origins.split(',')

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
app.include_router(webhook_router, prefix='/webhooks')
app.include_router(cache_router, prefix='/api')


@app.get('/health')
async def health_check():
    """Health check endpoint"""
    return JSONResponse(
        content={'status': 'healthy', 'service': 'call-processing'}, status_code=200
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

    return JSONResponse(
        status_code=500,
        content=error_message,
    )


environment = os.getenv('APP_ENV', 'dev')

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
