import glob

from dotenv import load_dotenv
from fastapi import FastAPI
import uvicorn

# ruff: noqa: E402
load_dotenv()  # Loading env values before importing modules to fix late read problem

from floware.app import (
    lifespan,
    register_exception_handlers,
    setup_openapi,
)
from floware.di import application_container
from floware.utils.config import csv
from floware.di.wiring import wire_containers
from floware.middleware.setup import add_middlewares
from floware.router import include_routers

config = application_container.config()
runtime = application_container.common.runtime_settings()
environment = runtime.app_env

# The interactive docs and the OpenAPI schema are off everywhere except dev,
# so a new/unknown APP_ENV value stays closed rather than exposing the surface.
is_dev = environment == 'dev'

app = FastAPI(
    lifespan=lifespan,
    openapi_url='/openapi.json' if is_dev else None,
    docs_url='/docs' if is_dev else None,
    redoc_url='/redoc' if is_dev else None,
)

# Telemetry providers are an ApplicationContainer resource, initialised with the
# container, so they exist before instrumentation is attached below.
setup_openapi(app, floware_base_url=runtime.floware_base_url)

add_middlewares(
    app,
    runtime=runtime,
    hmac_routes=csv(config['auth'].get('hmac_routes')),
    mtls_allowed_namespaces=csv(config['auth']['mtls_allowed_namespaces']),
)
include_routers(app)
register_exception_handlers(app, is_dev=is_dev)
wire_containers()

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
            workers=runtime.worker_count,
            log_level=runtime.uvicorn_log_level,
            forwarded_allow_ips='*',
        )
    else:
        dirs = glob.glob('../../..//**/*_module/**', recursive=True)
        dirs.extend(glob.glob('../../..//**/plugins/**', recursive=True))
        dirs.extend(glob.glob('../../..//**/packages/**', recursive=True))
        dirs.append('../../floware')

        uvicorn.run(
            'server:app',
            host=host,
            port=port,
            workers=1,
            reload=True,
            reload_includes=dirs,
            log_level=server['reload_log_level'],
            forwarded_allow_ips='*',
        )
