"""
Initializes all services once per worker process.
No DB connection owned by the worker — status updates go through Redis Streams.
Cloud / Redis / DB settings come from package config.ini.
"""

import threading
from dataclasses import dataclass
from typing import Optional

from dependency_injector import containers
from dependency_injector import providers

from api_services_module.api_services_container import ApiServicesContainer
from agents_module.agents_container import AgentsContainer
from agents_module.services.agent_inference_service import AgentInferenceService
from agents_module.services.workflow_inference_service import (
    WorkflowInferenceService,
)
from common_module.common_container import CommonContainer
from common_module.config_loader import is_truthy
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


def get_services() -> WorkerServices:
    global _services
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

        _services = WorkerServices(
            agent_inference=container.agents.agent_inference_service(),
            workflow_inference=container.agents.workflow_inference_service(),
            cloud_storage=container.common.cloud_storage_manager(),
            cache=container.db.cache_manager(),
            execution_bucket=bucket_name,
        )

    return _services
