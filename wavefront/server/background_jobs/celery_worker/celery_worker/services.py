"""
Initializes all services once per worker process.
No DB connection owned by the worker — status updates go through Redis Streams.
Cloud / Redis / DB settings come from package config.ini.
"""

import json
import threading
from dataclasses import dataclass
from typing import Optional

from dependency_injector import containers
from dependency_injector import providers

from api_services_module.api_services_container import ApiServicesContainer
from api_services_module.core.proxy import ApiProxy
from api_services_module.utils.api_change_publisher import (
    REDIS_API_SERVICE_UPDATES_CHANNEL,
)
from agents_module.agents_container import AgentsContainer
from agents_module.services.agent_inference_service import AgentInferenceService
from agents_module.services.workflow_inference_service import (
    WorkflowInferenceService,
)
from common_module.common_container import CommonContainer
from common_module.config_loader import is_truthy
from common_module.log.logger import logger
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.database.connection import DatabaseConfig, DatabaseClient
from db_repo_module.db_repo_container import DatabaseModuleContainer
from flo_cloud.cloud_storage import CloudStorageManager
from guardrails_module.bootstrap import start_presidio_regex_timeout
from guardrails_module.container import GuardrailsContainer
from llm_inference_config_module.container import LlmInferenceConfigContainer
from plugins_module.plugins_container import PluginsContainer
from tools_module.tools_container import ToolsContainer

from celery_worker.settings import CONFIG


@dataclass
class WorkerServices:
    agent_inference: AgentInferenceService
    workflow_inference: WorkflowInferenceService
    cloud_storage: CloudStorageManager
    cache: CacheManager
    execution_bucket: str


_lock = threading.Lock()
_services: Optional[WorkerServices] = None
_container: Optional['ApplicationContainer'] = None
_api_services_loaded = False


def _build_db_client(database: dict) -> DatabaseClient:
    return DatabaseClient(
        DatabaseConfig(
            username=database['username'],
            password=database['password'],
            host=database['host'],
            port=database['port'],
            db_name=database['db_name'],
            pool_size=database['pool_size'],
            max_overflow=database['max_overflow'],
            pool_timeout=database['pool_timeout'],
            pool_recycle=database['pool_recycle'],
        )
    )


def _guardrails_mode(enabled) -> str:
    return 'on' if is_truthy(enabled) else 'off'


def _guardrails_engine(selected):
    if selected is None:
        return None
    return selected.guardrails_engine()


class ApplicationContainer(containers.DeclarativeContainer):
    """Parent of the module containers the worker actually uses.

    Email OAuth and KMS are not used here (no trigger tasks). Those
    dependencies are stubbed so PluginsContainer still builds the message
    processor repository that agents and tools need.
    """

    config = providers.Configuration()

    presidio_regex_timeout = providers.Resource(
        start_presidio_regex_timeout,
        timeout=config.guardrails.regex_timeout_seconds,
    )

    db_client = providers.Singleton(_build_db_client, config.database)
    db = providers.Container(
        DatabaseModuleContainer,
        config=config,
        db_client=db_client,
    )
    common = providers.Container(
        CommonContainer,
        config=config,
        cache_manager=db.cache_manager,
    )
    guardrails = providers.Selector(
        providers.Callable(_guardrails_mode, config.guardrails.enabled),
        on=providers.Container(
            GuardrailsContainer,
            config=config,
            db_client=db.db_client,
            cache_manager=db.cache_manager,
        ),
        off=providers.Object(None),
    )
    plugins = providers.Container(
        PluginsContainer,
        config=config,
        db_client=db.db_client,
        cloud_storage_manager=common.cloud_storage_manager,
        kms_cipher=providers.Object(None),
        dynamic_query_repository=db.dynamic_query_repository,
        cache_manager=db.cache_manager,
        namespace_repository=db.namespace_repository,
        agentic_configuration_repository=db.agentic_configuration_repository,
        datasource_audit_log_repository=db.datasource_audit_log_repository,
        notification_repository=db.notification_repository,
        oauth_app_repository=providers.Object(None),
        email_connection_repository=db.email_connection_repository,
        feature_flags=common.feature_flags,
    )
    api_services = providers.Container(
        ApiServicesContainer,
        config=config,
        api_services_repository=db.api_services_repository,
        cloud_storage_manager=common.cloud_storage_manager,
        db_client=db.db_client,
        cache_manager=db.cache_manager,
        response_formatter=providers.Object(None),
    )
    tools = providers.Container(
        ToolsContainer,
        datasource_repository=db.datasource_repository,
        email_connection_repository=db.email_connection_repository,
        message_processor_repository=plugins.message_processor_repository,
        api_services_manager=api_services.api_service_manager,
        cloud_storage_manager=common.cloud_storage_manager,
        message_processor_bucket_name=config.storage.application_bucket,
        floware_base_url=config.env_config.base_url,
        passthrough_secret=config.env_config.passthrough_secret,
    )
    llm_inference_config = providers.Container(
        LlmInferenceConfigContainer,
        config=config,
        db_client=db.db_client,
        cache_manager=db.cache_manager,
        call_processing_cache_invalidator=common.call_processing_cache_invalidator,
    )
    agents = providers.Container(
        AgentsContainer,
        config=config,
        db_client=db.db_client,
        cloud_storage_manager=common.cloud_storage_manager,
        cache_manager=db.cache_manager,
        tool_loader=tools.tool_loader,
        namespace_repository=db.namespace_repository,
        agent_repository=db.agent_repository,
        agent_version_repository=db.agent_version_repository,
        workflow_repository=db.workflow_repository,
        workflow_version_repository=db.workflow_version_repository,
        message_processor_repository=plugins.message_processor_repository,
        message_processor_bucket_name=config.storage.application_bucket,
        api_services_manager=api_services.api_service_manager,
        async_agentic_execution_repository=db.async_agentic_execution_repository,
        executions_bucket=config.storage.application_bucket,
        llm_inference_config_service=llm_inference_config.llm_inference_config_service,
        guardrails_engine=providers.Callable(_guardrails_engine, guardrails),
    )


def _listen_for_api_service_updates(cache: CacheManager, proxy: ApiProxy) -> None:
    """Follow floware's API-service update channel, as floware's own listener does.

    The worker has no routes to reload and no event loop between tasks, so a
    change only evicts the service from this process's registry; the next
    trigger_api_service call loads the current definition from the database
    (ApiProxy loads a service it does not have on first use). That covers
    create, update and delete alike.
    """
    pubsub = cache.subscribe(channels=[REDIS_API_SERVICE_UPDATES_CHANNEL])

    def run():
        try:
            for message in pubsub.listen():
                if message.get('type') != 'message':
                    continue
                try:
                    service_id = json.loads(message['data'])['service_id']
                    proxy.remove_service(service_id)
                    logger.info(
                        f'API service {service_id} changed; reloads on next use'
                    )
                except Exception as e:
                    logger.error(f'Bad API service update message: {e}')
        except Exception as e:
            logger.error(f'API service update listener stopped: {e}')

    threading.Thread(target=run, name='api-service-updates', daemon=True).start()
    logger.info(f'Subscribed to Redis channel: {REDIS_API_SERVICE_UPDATES_CHANNEL}')


def load_api_services() -> None:
    """Load every API service into this process's registry, as floware does at startup.

    Called once the worker is up (signals.py), outside any running event loop.
    Updates after that arrive on the update channel, and a service missing for
    any reason still loads on first use, so a failure here is logged, not raised.
    """
    global _api_services_loaded
    from celery_worker.event_loop import get_event_loop

    with _lock:
        if _api_services_loaded:
            return
        _api_services_loaded = True
    get_services()
    try:
        registry = _container.api_services.initialized_service_registry()
        get_event_loop().run_until_complete(registry.load_from_db())
        proxy = _container.api_services.api_proxy()
        for service in registry.get_all_services().values():
            proxy.auth_manager.register_service_auth(service)
        logger.info(f'Loaded {len(registry.get_all_services())} API services')
    except Exception as e:
        logger.warning(f'Failed to load API services at startup: {e}')


def get_services() -> WorkerServices:
    global _services, _container
    if _services is not None:
        return _services

    with _lock:
        if _services is not None:
            return _services

        bucket_name = CONFIG['storage']['application_bucket']
        if not bucket_name:
            raise ValueError(
                'storage.application_bucket (APPLICATION_BUCKET) must be set in config.ini'
            )

        container = ApplicationContainer()
        container.config.from_dict(CONFIG)
        container.init_resources()
        # trigger_api_service nodes call execute_api_service, which takes the
        # ApiProxy by injection (Provide[...]); without this wiring a workflow run
        # by the worker gets the unresolved marker and fails with "'Provide'
        # object has no attribute 'process_request'". Same wiring as floware's.
        container.api_services.wire(
            modules=['api_services_module.api_services_container'],
            packages=['api_services_module.core', 'api_services_module.execution'],
        )
        _listen_for_api_service_updates(
            container.db.cache_manager(), container.api_services.api_proxy()
        )

        _container = container
        _services = WorkerServices(
            agent_inference=container.agents.agent_inference_service(),
            workflow_inference=container.agents.workflow_inference_service(),
            cloud_storage=container.common.cloud_storage_manager(),
            cache=container.db.cache_manager(),
            execution_bucket=bucket_name,
        )

    return _services
