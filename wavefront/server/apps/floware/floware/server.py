from contextlib import asynccontextmanager
import glob
import os
import asyncio
from typing import Any, Callable, cast

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

import uvicorn

# ruff: noqa: E402
load_dotenv()  # Loading env values before importing modules to fix late read problem

from auth_module.auth_container import AuthContainer
from auth_module.controllers.outlook_controller import subscription_controller
from auth_module.controllers.superset_controller import superset_controller
from auth_module.controllers.hmac_controller import hmac_router
from common_module.common_container import CommonContainer
from common_module.middleware.request_id_middleware import (
    RequestIdMiddleware,
    get_current_request_id,
)
from common_module.log.logger import logger
from common_module.prometheus.prometheus_middleware import PrometheusMiddleware
from common_module.response_formatter import ResponseFormatter
from db_repo_module.database.connection import DatabaseClient
from db_repo_module.db_repo_container import DatabaseModuleContainer
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse
from gold_module.controllers.router import gold_router
from gold_module.gold_container import GoldContainer
from insights_module.controllers.router import insights_router
from insights_module.insights_container import InsightsContainer

from knowledge_base_module.controllers.knowledge_base_controller import (
    knowledge_base_router,
)
from knowledge_base_module.controllers.knowledge_base_document_controller import (
    kb_document_router,
)
from knowledge_base_module.controllers.rag_retreival_controller import (
    rag_retrieval_router,
)
from knowledge_base_module.knowledge_base_container import KnowledgeBaseContainer
from user_management_module.authorization.require_auth import RequireAuthMiddleware
from user_management_module.router import user_management_router
from user_management_module.user_container import UserContainer

from floware.controllers.notification_controller import notification_router
from floware.di.application_container import ApplicationContainer
from floware.middleware.security_headers import SecurityHeadersMiddleware
from plugins_module.plugins_container import PluginsContainer
from plugins_module.controllers.datasource_controller import datasource_router
from plugins_module.controllers.authenticator_controller import authenticator_router
from floware.controllers.config_controller import config_router
from product_analysis_module.controllers.product_anaysis_controllers import (
    product_analysis_router,
)
from product_analysis_module.product_analysis_container import ProductAnalysisContainer

from agents_module.controllers.agent_controller import agents_router
from agents_module.controllers.namespace_controller import namespace_router
from agents_module.controllers.workflow_controller import workflows_router
from agents_module.controllers.workflow_runs import workflow_runs_router
from agents_module.controllers.workflow_pipeline_controller import (
    workflow_pipeline_router,
)
from agents_module.agents_container import AgentsContainer
from inference_module.inference_container import InferenceContainer
from inference_module.controllers.inference_controller import inference_router

from llm_inference_config_module.container import LlmInferenceConfigContainer
from llm_inference_config_module.controllers.llm_inference_config_controller import (
    llm_inference_config_router,
)
from llm_inference_config_module.controllers.inference_proxy_controller import (
    inference_proxy_router,
)
from tools_module.controllers.tools_controller import tools_router
from tools_module.tools_container import ToolsContainer
from voice_agents_module.voice_agents_container import VoiceAgentsContainer
from voice_agents_module.controllers.telephony_config_controller import (
    telephony_config_router,
)
from voice_agents_module.controllers.tts_config_controller import tts_config_router
from voice_agents_module.controllers.stt_config_controller import stt_config_router
from voice_agents_module.controllers.voice_agent_controller import voice_agent_router
from plugins_module.controllers.message_processor_controller import (
    message_processor_router,
)

# API Services Module
from api_services_module.api_services_container import create_api_services_container
from api_services_module.api_services_container import ApiServicesContainer
from floware.channels import start_redis_listener
from starlette.middleware import _MiddlewareFactory

# Initialize dependency containers
# Create a single shared instance of the database container
db_repo_container = DatabaseModuleContainer()
auth_container = AuthContainer(
    db_client=db_repo_container.db_client, cache_manager=db_repo_container.cache_manager
)
common_container = CommonContainer(cache_manager=db_repo_container.cache_manager)
user_module_container = UserContainer(
    db_client=db_repo_container.db_client, cache_manager=db_repo_container.cache_manager
)
insights_container = InsightsContainer(
    notification_repository=db_repo_container.notification_repository,
    cache_manager=db_repo_container.cache_manager,
)


application_container = ApplicationContainer(
    db_client=db_repo_container.db_client,
    email_repository=db_repo_container.email_repository,
    oauth_credential_repository=db_repo_container.oauth_credential_repository,
    user_repository=db_repo_container.user_repository,
    task_repository=db_repo_container.task_repository,
    insights_service=insights_container.insights_service,
    pvo_repository=insights_container.pvo_repository,
    notification_repository=db_repo_container.notification_repository,
    notification_user_repository=db_repo_container.notification_user_repository,
    config_repository=db_repo_container.config_repository,
)

email_rag_container = KnowledgeBaseContainer(
    db_client=db_repo_container.db_client, cache_manager=db_repo_container.cache_manager
)

gold_container = GoldContainer()

plugins_container = PluginsContainer(
    db_client=db_repo_container.db_client,
    cloud_manager=common_container.cloud_storage_manager,
    dynamic_query_repository=db_repo_container.dynamic_query_repository,
    cache_manager=db_repo_container.cache_manager,
)

product_analysis_container = ProductAnalysisContainer()

tools_container = ToolsContainer(
    datasource_repository=db_repo_container.datasource_repository,
    knowledge_base_repository=db_repo_container.knowledge_base_repository,
    knowledge_base_inference_repository=db_repo_container.knowledge_base_inference_repository,
)

agents_container = AgentsContainer(
    db_client=db_repo_container.db_client,
    cloud_storage_manager=common_container.cloud_storage_manager,
    cache_manager=db_repo_container.cache_manager,
    tool_loader=tools_container.tool_loader,
    workflow_pipeline_repository=db_repo_container.workflow_pipeline_repository,
    workflow_runs_repository=db_repo_container.workflow_runs_repository,
    namespace_repository=db_repo_container.namespace_repository,
    agent_repository=db_repo_container.agent_repository,
    workflow_repository=db_repo_container.workflow_repository,
)

inference_container = InferenceContainer(
    db_client=db_repo_container.db_client,
    cache_manager=db_repo_container.cache_manager,
)

llm_inference_config_container = LlmInferenceConfigContainer(
    db_client=db_repo_container.db_client,
    cache_manager=db_repo_container.cache_manager,
)

# API Services Container
api_services_container: ApiServicesContainer = create_api_services_container(
    api_service_repository=db_repo_container.api_services_repository,
    cloud_storage_manager=common_container.cloud_storage_manager,
    db_client=db_repo_container.db_client,
    cache_manager=db_repo_container.cache_manager,
    response_formatter=common_container.response_formatter,
)

voice_agents_container = VoiceAgentsContainer(
    db_client=db_repo_container.db_client,
    cache_manager=db_repo_container.cache_manager,
    cloud_storage_manager=common_container.cloud_storage_manager,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup code (runs before the application starts)
    logger.info('Starting application...')

    try:
        db_client: DatabaseClient = db_repo_container.db_client()

        if isinstance(db_client, DatabaseClient):
            logger.info('========== Establishing db connection ...')
            await db_client.connect()
            logger.info('========== DB connection established.')
        else:
            raise TypeError('db_client is not an instance of DatabaseClient')

        db_client.run_migration()

        # Instantiate scheduler from container when needed
        scheduler = common_container.scheduler()
        scheduler.start_scheduler()
        logger.info('Database connection established.')

        # Load API services from database into registry
        service_registry = api_services_container.initialized_service_registry()
        if getattr(service_registry, 'api_service_manager', None):
            try:
                await service_registry.load_from_db()
                logger.info('API services loaded from database')

                # Reload routes to include newly loaded services
                proxy_router = api_services_container.proxy_router()
                proxy_router.reload_routes()
                logger.info('API service routes reloaded')
            except Exception as e:
                logger.warning(f'Failed to load API services from database: {e}')

        api_services_container.initialized_proxy()

        # Include API services router AFTER services are loaded so routes are registered
        # This ensures FastAPI's route table includes the dynamic routes
        app.include_router(
            api_services_container.router(), tags=['API Services'], prefix='/floware'
        )
        logger.info('API services router included in app')

        # Start background Redis listener for updates
        asyncio.create_task(
            start_redis_listener(
                cache_manager=db_repo_container.cache_manager(),
                api_change_processor=api_services_container.api_change_processor(),
            )
        )

        # Set app reference in proxy router so new routes can be added dynamically
        proxy_router = api_services_container.proxy_router()
        proxy_router.set_app(app, prefix='/floware')
        logger.info('App reference set in proxy router for dynamic route registration')

        yield  # This is where the application runs

        # Shutdown code
        logger.info('Shutting down application...')

    except Exception as e:
        logger.error(f'Error during application lifecycle: {str(e)}')
        raise


# Define FastAPI app with the lifespan context manager
app = FastAPI(lifespan=lifespan)

floware_base_url = os.getenv('FLOWARE_BASE_URL', 'http://localhost:8001')


def _middleware(cls: type[Any]) -> _MiddlewareFactory[Any]:
    return cast(_MiddlewareFactory[Any], cls)


OpenApiCallable = Callable[[], dict[str, Any]]


def custom_openapi() -> dict[str, Any]:
    """Custom OpenAPI schema with Bearer authentication"""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title='Flo API',
        version='1.0.0',
        description='Floware Server - AI Middleware API',
        routes=app.routes,
        servers=[{'url': floware_base_url, 'description': 'floware server'}],
    )

    # Add Bearer authentication security scheme
    # This matches the scheme_name in BearerAuth class
    openapi_schema['components']['securitySchemes'] = {
        'BearerAuth': {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
            'description': 'Enter your JWT token',
        }
    }

    # Apply security to all endpoints by default
    # Individual endpoints can override this with dependencies=[]
    # openapi_schema["security"] = [{"BearerAuth": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = cast(OpenApiCallable, custom_openapi)  # type: ignore[assignment]


@app.get('/v1/_metrics')
async def metrics(request: Request):
    logger.debug('Metrics endpoint called')
    metrics_data = await PrometheusMiddleware.metrics_endpoint(request)
    return metrics_data


# Add middleware setup

app.add_middleware(_middleware(RequestIdMiddleware))
app.add_middleware(_middleware(RequireAuthMiddleware))
app.add_middleware(_middleware(PrometheusMiddleware))
app.add_middleware(_middleware(SecurityHeadersMiddleware))  # disable to see swaggerUI

origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173')
allowed_origins = origins.split(',')

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
app.include_router(notification_router, prefix='/floware')
app.include_router(user_management_router, prefix='/floware')
app.include_router(superset_controller, prefix='/floware')
app.include_router(insights_router, prefix='/floware')
app.include_router(knowledge_base_router, prefix='/floware')
app.include_router(kb_document_router, prefix='/floware')
app.include_router(rag_retrieval_router, prefix='/floware')
app.include_router(gold_router, prefix='/floware')
app.include_router(subscription_controller, prefix='/floware')
app.include_router(datasource_router, prefix='/floware')
app.include_router(hmac_router, prefix='/floware')
app.include_router(authenticator_router, prefix='/floware')
app.include_router(config_router, prefix='/floware')
app.include_router(product_analysis_router, prefix='/floware')
app.include_router(agents_router, prefix='/floware')
app.include_router(namespace_router, prefix='/floware')
app.include_router(workflows_router, prefix='/floware')
app.include_router(workflow_pipeline_router, prefix='/floware')
app.include_router(workflow_runs_router, prefix='/floware')
app.include_router(inference_router, prefix='/floware')

app.include_router(llm_inference_config_router, prefix='/floware')
app.include_router(inference_proxy_router, prefix='/floware')
app.include_router(tools_router, prefix='/floware')
app.include_router(telephony_config_router, prefix='/floware')
app.include_router(tts_config_router, prefix='/floware')
app.include_router(stt_config_router, prefix='/floware')
app.include_router(voice_agent_router, prefix='/floware')
app.include_router(message_processor_router, prefix='/floware')


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Skip HTTPExceptions (they're handled by FastAPI)
    if isinstance(exc, HTTPException):
        raise exc

    prometheus_middleware = PrometheusMiddleware.get_instance()
    if prometheus_middleware:
        labels = prometheus_middleware.get_labels(request)
        prometheus_middleware.http_errors_total.labels(**labels, status_code=500).inc()

    error_message = 'An unexpected error has occurred while performing this action, please try again'
    error_message += f' - {str(exc)}'

    request_id = getattr(request.state, 'request_id', get_current_request_id())
    logger.error(f'Error in API call [Request ID: {request_id}]: {exc}', exc_info=True)

    exception_response_formatter = ResponseFormatter()
    return JSONResponse(
        status_code=500,
        content=exception_response_formatter.buildErrorResponse(error=error_message),
    )


# Wire dependency injection
application_container.wire(modules=[__name__], packages=['floware.controllers'])

db_repo_container.wire(
    modules=[__name__],
    packages=[
        'product_analysis_module.product_analysis_service',
    ],
)


product_analysis_container.wire(
    modules=[__name__],
    packages=['product_analysis_module.controllers'],
)

user_module_container.wire(
    modules=[__name__],
    packages=[
        'auth_module.controllers',
        'plugins_module.controllers',
        'insights_module.controllers',
        'user_management_module.controllers',
        'user_management_module.authorization',
        'plugins_module.controllers',
    ],
)

auth_container.wire(
    modules=[__name__],
    packages=[
        'auth_module.controllers',
        'user_management_module.authorization',
        'user_management_module.controllers',
        'insights_module.controllers',
        'plugins_module.services',
        'plugins_module.controllers',
        'llm_inference_config_module.controllers',
    ],
)

insights_container.wire(
    modules=[__name__],
    packages=['insights_module.controllers'],
)

gold_container.wire(
    modules=[__name__],
    packages=['gold_module.controllers'],
)

common_container.wire(
    modules=[__name__],
    packages=[
        'auth_module.controllers',
        'user_management_module.controllers',
        'user_management_module.authorization',
        'insights_module.controllers',
        'floware.controllers',
        'knowledge_base_module.controllers',
        'gold_module.controllers',
        'plugins_module.controllers',
        'plugins_module.services',
        'product_analysis_module.controllers',
        'agents_module.controllers',
        'agents_module.services',
        'inference_module.controllers',
        'llm_inference_config_module.controllers',
        'tools_module.controllers',
        'voice_agents_module.controllers',
    ],
)

email_rag_container.wire(
    modules=[__name__],
    packages=[
        'knowledge_base_module.controllers',
        'auth_module.controllers',
        'inference_module.controllers',
    ],
)

plugins_container.wire(
    modules=[__name__],
    packages=[
        'plugins_module.controllers',
        'plugins_module.services',
        'user_management_module.controllers',
        'user_management_module.authorization',
        'tools_module.datasources',
    ],
)

agents_container.wire(
    modules=[__name__],
    packages=[
        'agents_module.controllers',
        'agents_module.services',
    ],
)

inference_container.wire(
    modules=[__name__],
    packages=['inference_module.controllers'],
)

llm_inference_config_container.wire(
    modules=[__name__],
    packages=[
        'llm_inference_config_module.controllers',
        'agents_module.controllers',
        'knowledge_base_module.controllers',
    ],
)

tools_container.wire(
    modules=[__name__],
    packages=[
        'tools_module.controllers',
    ],
)

api_services_container.wire(
    modules=[__name__],
    packages=['api_services_module.core'],
)

voice_agents_container.wire(
    modules=[__name__],
    packages=[
        'voice_agents_module.controllers',
        'voice_agents_module.services',
    ],
)

environment = os.getenv('APP_ENV', 'dev')

# Running with Uvicorn (for local development)
if __name__ == '__main__':
    print(f'Starting application in environment: {environment}')
    if environment == 'production':
        uvicorn.run(
            'server:app',
            host='0.0.0.0',
            port=8001,
            workers=4,
            log_level='critical',
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
