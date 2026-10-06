from contextlib import asynccontextmanager
import glob
import asyncio
from typing import Any, Callable, cast

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

import uvicorn

# ruff: noqa: E402
load_dotenv()  # Loading env values before importing modules to fix late read problem

from auth_module.auth_container import AuthContainer
from common_module.common_container import CommonContainer
from common_module.middleware.request_id_middleware import get_current_request_id
from common_module.log.logger import configure_logging, logger
from common_module.feature.feature_flag import configure_feature_flags
from common_module.telemetry import (
    TelemetrySettings,
    configure_telemetry_providers,
    instrument_sqlalchemy,
    record_exception_on_span,
    shutdown_telemetry,
)
from common_module.utils.odata_settings import configure_odata_cloud_provider
from agents_module.runtime_config import (
    configure_azure_openai_api_version,
    configure_celery_broker,
)
from common_module.response_formatter import ResponseFormatter

from db_repo_module.database.connection import DatabaseClient
from db_repo_module.db_repo_container import DatabaseModuleContainer
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse
from gold_module.gold_container import GoldContainer

from knowledge_base_module.knowledge_base_container import KnowledgeBaseContainer
from knowledge_base_module.services.kb_index_status_consumer import (
    KbIndexStatusConsumer,
)
from user_management_module.user_container import UserContainer
from user_management_module.authorization.require_auth import (
    DEFAULT_MTLS_ALLOWED_NAMESPACES,
    configure_jwt_auth_settings,
)
from floware.di.application_container import ApplicationContainer
from floware.middleware.setup import add_middlewares
from floware.routes import include_routers
from floware.services.scheduler_manager import SchedulerManager
from plugins_module.plugins_container import PluginsContainer
from product_analysis_module.product_analysis_container import ProductAnalysisContainer

from agents_module.services.async_agentic_execution_result_consumer import (
    AsyncAgenticExecutionResultConsumer,
)
from agents_module.agents_container import AgentsContainer
from inference_module.inference_container import InferenceContainer

from flo_ai.llm.guarded_llm import GuardrailBlocked
from guardrails_module.container import GuardrailsContainer
from llm_inference_config_module.container import LlmInferenceConfigContainer
from tools_module.tools_container import ToolsContainer
from chatbots_module.chatbots_container import ChatbotsContainer
from voice_agents_module.voice_agents_container import VoiceAgentsContainer

# API Services Module
from api_services_module.api_services_container import create_api_services_container
from api_services_module.api_services_container import ApiServicesContainer
from floware.channels import start_redis_listener


def _csv(value: str | None, default: tuple[str, ...] = ()) -> list[str]:
    """Split a comma-separated config value; ``default`` when it is not set."""
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(',') if item.strip()]


# Initialize dependency containers
# Create a single shared instance of the database container
db_repo_container = DatabaseModuleContainer()
common_container = CommonContainer(cache_manager=db_repo_container.cache_manager)
config = common_container.config()
runtime = common_container.runtime_settings()
configure_feature_flags(**(config.get('feature_flags') or {}))
configure_odata_cloud_provider(config['cloud']['provider'])
configure_celery_broker(config['celery']['broker_url'])
configure_azure_openai_api_version(
    (config.get('model') or {}).get('azure_openai_api_version')
)
configure_logging(
    app_name=config['env_config']['app_name'],
    log_level=config['env_config'].get('log_level') or 'INFO',
)
configure_jwt_auth_settings(
    validation_issuer=config['jwt_token']['validation_issuer'],
    audience=config['jwt_token']['audience'],
    token_prefix=config['jwt_token'].get('console_token_prefix', 'fc_'),
)
auth_container = AuthContainer(
    db_client=db_repo_container.db_client,
    cache_manager=db_repo_container.cache_manager,
    kms_signer=common_container.kms_signer,
)
# Built before the containers that send email: both the platform mailer and
# scheduled jobs send through this container's email_send_service.
plugins_container = PluginsContainer(
    db_client=db_repo_container.db_client,
    cloud_storage_manager=common_container.cloud_storage_manager,
    kms_cipher=common_container.kms_cipher,
    dynamic_query_repository=db_repo_container.dynamic_query_repository,
    cache_manager=db_repo_container.cache_manager,
    namespace_repository=db_repo_container.namespace_repository,
    agentic_configuration_repository=db_repo_container.agentic_configuration_repository,
    datasource_audit_log_repository=db_repo_container.datasource_audit_log_repository,
    notification_repository=db_repo_container.notification_repository,
    oauth_app_repository=db_repo_container.oauth_app_repository,
    email_connection_repository=db_repo_container.email_connection_repository,
)

user_module_container = UserContainer(
    db_client=db_repo_container.db_client,
    cache_manager=db_repo_container.cache_manager,
    email_send_service=plugins_container.email_send_service,
)
application_container = ApplicationContainer(
    db_client=db_repo_container.db_client,
    cache_manager=db_repo_container.cache_manager,
    cloud_storage_manager=common_container.cloud_storage_manager,
    user_repository=db_repo_container.user_repository,
    task_repository=db_repo_container.task_repository,
    notification_repository=db_repo_container.notification_repository,
    notification_user_repository=db_repo_container.notification_user_repository,
    config_repository=db_repo_container.config_repository,
    scheduled_job_repository=db_repo_container.scheduled_job_repository,
    scheduled_job_execution_repository=db_repo_container.scheduled_job_execution_repository,
    datasource_repository=db_repo_container.datasource_repository,
    dynamic_query_repository=db_repo_container.dynamic_query_repository,
    email_send_service=plugins_container.email_send_service,
    email_connection_service=plugins_container.email_connection_service,
    user_service=user_module_container.user_service,
    role_repository=user_module_container.role_repository,
    user_role_repository=user_module_container.user_role_repository,
    knowledge_base_repository=db_repo_container.knowledge_base_repository,
)

knowledge_base_container = KnowledgeBaseContainer(
    db_client=db_repo_container.db_client,
    ingestion_db_client=db_repo_container.ingestion_db_client,
    cache_manager=db_repo_container.cache_manager,
    cloud_storage_manager=common_container.cloud_storage_manager,
    rag_queue=common_container.rag_queue,
)

gold_container = GoldContainer(
    cloud_storage_manager=common_container.cloud_storage_manager,
    gold_queue=common_container.gold_queue,
)

product_analysis_container = ProductAnalysisContainer()
product_analysis_container.config.from_dict(config)

# API Services Container (must be created before tools_container)
api_services_container: ApiServicesContainer = create_api_services_container(
    api_service_repository=db_repo_container.api_services_repository,
    cloud_storage_manager=common_container.cloud_storage_manager,
    db_client=db_repo_container.db_client,
    cache_manager=db_repo_container.cache_manager,
    response_formatter=common_container.response_formatter,
)

bucket_name = config['storage']['application_bucket']

tools_container = ToolsContainer(
    datasource_repository=db_repo_container.datasource_repository,
    email_connection_repository=db_repo_container.email_connection_repository,
    message_processor_repository=plugins_container.message_processor_repository,
    api_services_manager=api_services_container.api_service_manager,
    cloud_storage_manager=common_container.cloud_storage_manager,
    message_processor_bucket_name=bucket_name,
    floware_base_url=runtime.floware_base_url,
    passthrough_secret=runtime.passthrough_secret,
)

inference_container = InferenceContainer(
    db_client=db_repo_container.db_client,
    cache_manager=db_repo_container.cache_manager,
)

llm_inference_config_container = LlmInferenceConfigContainer(
    db_client=db_repo_container.db_client,
    cache_manager=db_repo_container.cache_manager,
    call_processing_cache_invalidator=common_container.call_processing_cache_invalidator,
)

guardrails_container = GuardrailsContainer(
    db_client=db_repo_container.db_client,
    cache_manager=db_repo_container.cache_manager,
)
guardrails_container.config.from_dict(config)

agents_container = AgentsContainer(
    db_client=db_repo_container.db_client,
    cloud_storage_manager=common_container.cloud_storage_manager,
    cache_manager=db_repo_container.cache_manager,
    tool_loader=tools_container.tool_loader,
    namespace_repository=db_repo_container.namespace_repository,
    agent_repository=db_repo_container.agent_repository,
    agent_version_repository=db_repo_container.agent_version_repository,
    workflow_repository=db_repo_container.workflow_repository,
    workflow_version_repository=db_repo_container.workflow_version_repository,
    message_processor_repository=plugins_container.message_processor_repository,
    message_processor_bucket_name=bucket_name,
    api_services_manager=api_services_container.api_service_manager,
    async_agentic_execution_repository=db_repo_container.async_agentic_execution_repository,
    executions_bucket=config['storage']['application_bucket'],
    llm_inference_config_service=llm_inference_config_container.llm_inference_config_service,
    guardrails_engine=guardrails_container.guardrails_engine,
)

voice_agents_container = VoiceAgentsContainer(
    db_client=db_repo_container.db_client,
    cache_manager=db_repo_container.cache_manager,
    cloud_storage_manager=common_container.cloud_storage_manager,
    call_processing_cache_invalidator=common_container.call_processing_cache_invalidator,
)
voice_agents_container.config.from_dict(config)

chatbots_container = ChatbotsContainer(
    db_client=db_repo_container.db_client,
    cache_manager=db_repo_container.cache_manager,
    llm_inference_config_service=llm_inference_config_container.llm_inference_config_service,
)

scheduler_manager = SchedulerManager()


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
            # Emits db.* spans for every query; needs the engine, so it can
            # only happen once the DI container has built the client.
            instrument_sqlalchemy(db_client.engine)
        else:
            raise TypeError('db_client is not an instance of DatabaseClient')

        db_client.run_migration()

        # Load the safety providers' models before the first request needs
        # them. Presidio builds a spaCy model on first use, which takes longer
        # than the per-check timeout the policy sets — so without this the
        # first checked request times out and, under a FAIL_CLOSED policy, is
        # rejected. Paid here, where nothing is waiting on it.
        await guardrails_container.guardrails_engine().warmup()

        scheduled_job_service = application_container.scheduled_job_service()

        # Run stale lock recovery once on startup before the scheduler ticks.
        await scheduled_job_service.recover_stale_locks()

        scheduler_manager.start()
        scheduler_manager.register_due_jobs_poller(
            callback=scheduled_job_service.process_due_jobs_sync
        )
        scheduler_manager.register_stale_lock_recovery(
            callback=scheduled_job_service.recover_stale_locks_sync
        )
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

        # Start Redis Stream consumer for async execution status updates
        streams = config['streams']
        async_agentic_exec_consumer = AsyncAgenticExecutionResultConsumer(
            exec_repo=db_repo_container.async_agentic_execution_repository(),
            cache_manager=db_repo_container.cache_manager(),
            stream=streams['async_agentic_exec_results'],
            group=streams.get('async_agentic_exec_consumer_group')
            or 'floware-agentic-consumers',
            poll_interval_s=float(
                streams.get('async_agentic_exec_poll_interval_s') or 5
            ),
            heartbeat_interval_s=int(
                streams.get('async_agentic_exec_heartbeat_s') or 60
            ),
        )
        async_agentic_exec_consumer_task = asyncio.create_task(
            async_agentic_exec_consumer.start()
        )

        # Start Redis Stream consumer for knowledge base document index statuses
        kb_index_status_consumer = KbIndexStatusConsumer(
            documents_repo=knowledge_base_container.knowledge_base_documents_repository(),
            cache_manager=db_repo_container.cache_manager(),
            group=streams.get('kb_index_status_consumer_group')
            or 'floware-kb-index-status',
            poll_interval_s=float(streams.get('kb_index_status_poll_interval_s') or 5),
            heartbeat_interval_s=int(streams.get('kb_index_status_heartbeat_s') or 60),
            reclaim_interval_s=float(
                streams.get('kb_index_status_reclaim_interval_s') or 60
            ),
            reclaim_min_idle_ms=int(
                streams.get('kb_index_status_reclaim_min_idle_ms') or 60000
            ),
            max_deliveries=int(streams.get('kb_index_status_max_deliveries') or 5),
        )
        kb_index_status_consumer_task = asyncio.create_task(
            kb_index_status_consumer.start()
        )

        # Set app reference in proxy router so new routes can be added dynamically
        proxy_router = api_services_container.proxy_router()
        proxy_router.set_app(app, prefix='/floware')
        logger.info('App reference set in proxy router for dynamic route registration')

        yield  # This is where the application runs

        # Shutdown code
        scheduler_manager.shutdown()
        async_agentic_exec_consumer.stop()
        try:
            await asyncio.wait_for(async_agentic_exec_consumer_task, timeout=5)
        except asyncio.TimeoutError:
            async_agentic_exec_consumer_task.cancel()
            logger.warning(
                'AsyncAgenticExecutionResultConsumer did not stop within 5s; cancelled'
            )
        kb_index_status_consumer.stop()
        try:
            await asyncio.wait_for(kb_index_status_consumer_task, timeout=5)
        except asyncio.TimeoutError:
            kb_index_status_consumer_task.cancel()
            logger.warning('KbIndexStatusConsumer did not stop within 5s; cancelled')
        logger.info('Shutting down application...')

    except Exception as e:
        logger.error(f'Error during application lifecycle: {str(e)}')
        raise
    finally:
        # In a `finally` so buffered spans and metrics are still flushed when
        # shutdown takes an error path or startup fails before `yield`.
        shutdown_telemetry()


environment = runtime.app_env

# The interactive docs and the OpenAPI schema are off everywhere except dev,
# so a new/unknown APP_ENV value stays closed rather than exposing the surface.
is_dev = environment == 'dev'

# Define FastAPI app with the lifespan context manager
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
        servers=[{'url': runtime.floware_base_url, 'description': 'floware server'}],
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


# Middlewares & Routers
add_middlewares(
    app,
    runtime=runtime,
    hmac_routes=_csv(config['auth'].get('hmac_routes')),
    mtls_allowed_namespaces=_csv(
        config['auth'].get('mtls_allowed_namespaces'),
        DEFAULT_MTLS_ALLOWED_NAMESPACES,
    ),
)
include_routers(app)


@app.exception_handler(GuardrailBlocked)
async def guardrail_blocked_handler(request: Request, exc: GuardrailBlocked):
    """Turn a policy block into a plain error response.

    A block is the guardrail working, not the server failing. Left to the
    catch-all below, it arrives as an unhandled exception: a ~100-frame
    traceback logged twice — once by that handler's ``exc_info``, then again
    by uvicorn, because Starlette re-raises whatever reaches its 500 handler
    — for an outcome whose whole explanation fits on one line.

    Which adapter fired, on which finding, under which policy version goes to
    the log only. The response carries the decision's own caller message,
    which deliberately names none of that: telling whoever tripped a check
    exactly which check they tripped is a map of how to phrase the next
    attempt.
    """
    request_id = getattr(request.state, 'request_id', get_current_request_id())
    detail = exc.decision.operator_summary() if exc.decision else str(exc)

    # A content block is the control doing its job. A block because a check
    # could not run - provider down with FAIL_CLOSED, or a policy naming an
    # adapter that is not registered - is rejecting legitimate traffic until
    # someone intervenes, and stays at error level so alerting still sees it.
    emit = (
        logger.error
        if exc.decision is not None and exc.decision.blocked_by_failure
        else logger.warning
    )
    emit(
        f'Guardrail blocked {request.method} {request.url.path} '
        f'[Request ID: {request_id}]: {detail}'
    )

    return JSONResponse(
        status_code=500,
        content=ResponseFormatter().buildErrorResponse(error=str(exc)),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Skip HTTPExceptions (they're handled by FastAPI)
    if isinstance(exc, HTTPException):
        raise exc

    # This handler swallows the exception and returns a 500 without re-raising,
    # so it never reaches the OTel ASGI middleware's own exception recording -
    # the SERVER span would otherwise be marked as a success. Record it here.
    record_exception_on_span(exc)

    error_message = 'An unexpected error has occurred while performing this action, please try again'
    if is_dev:
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
        'user_management_module.controllers',
        'user_management_module.authorization',
        # Helpers in utils (check_is_admin and its callers) resolve container
        # providers themselves, so the package needs wiring too — otherwise only
        # the copies imported into wired controller modules get patched.
        'user_management_module.utils',
        'plugins_module.controllers',
    ],
)

auth_container.wire(
    modules=[__name__],
    packages=[
        'auth_module.controllers',
        'user_management_module.authorization',
        'user_management_module.controllers',
        'plugins_module.services',
        'plugins_module.controllers',
        'llm_inference_config_module.controllers',
    ],
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
        'chatbots_module.controllers',
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
        'guardrails_module.controllers',
        'tools_module.controllers',
        'voice_agents_module.controllers',
    ],
)

knowledge_base_container.wire(
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
        'floware.controllers',
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

guardrails_container.wire(
    modules=[__name__],
    packages=[
        'guardrails_module.controllers',
        # Agent inference resolves policy when constructing a guarded LLM.
        'agents_module.controllers',
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

chatbots_container.wire(
    modules=[__name__],
    packages=[
        'chatbots_module.controllers',
    ],
)
# Running with Uvicorn (for local development)
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
