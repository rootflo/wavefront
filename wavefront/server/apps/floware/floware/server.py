import glob

from dotenv import load_dotenv
from fastapi import FastAPI
import uvicorn

# ruff: noqa: E402
load_dotenv()  # Loading env values before importing modules to fix late read problem

from common_module.telemetry import (
    TelemetrySettings,
    configure_telemetry_providers,
)
from floware.app import (
    lifespan,
    register_exception_handlers,
    setup_openapi,
)
from floware.di.containers import config, csv, runtime
from floware.di.wiring import wire_containers
from floware.middleware.setup import add_middlewares
from floware.router import include_routers
from user_management_module.authorization.require_auth import (
    DEFAULT_MTLS_ALLOWED_NAMESPACES,
)

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

# Providers must exist before any instrumentation is attached. The FastAPI app
# itself is instrumented further down, after all other middleware is registered.
configure_telemetry_providers(
    TelemetrySettings.from_config(
        config, default_service_name=config['env_config']['app_name']
    )
)

setup_openapi(app, floware_base_url=runtime.floware_base_url)

add_middlewares(
    app,
    runtime=runtime,
    hmac_routes=csv(config['auth'].get('hmac_routes')),
    mtls_allowed_namespaces=csv(
        config['auth'].get('mtls_allowed_namespaces'),
        DEFAULT_MTLS_ALLOWED_NAMESPACES,
    ),
)
include_routers(app)
register_exception_handlers(app, is_dev=is_dev)
wire_containers()

if __name__ == '__main__':
    print(f'Starting application in environment: {environment}')
    if environment == 'production':
        uvicorn.run(
            'server:app',
            host='0.0.0.0',
            port=8001,
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
            host='0.0.0.0',
            port=8001,
            workers=1,
            reload=True,
            reload_includes=dirs,
            log_level='info',
            forwarded_allow_ips='*',
        )
