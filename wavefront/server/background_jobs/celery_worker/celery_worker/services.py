"""
Initializes all services once per worker process.
No DB connection owned by the worker — status updates go through Redis Streams.
Cloud / Redis / DB settings come from package config.ini.
"""

import threading
from dataclasses import dataclass
from typing import Optional

from dependency_injector import providers

from api_services_module.api_services_container import (
    ApiServicesContainer,
    create_api_services_container,
)
from agents_module.agents_container import AgentsContainer
from llm_inference_config_module.container import LlmInferenceConfigContainer
from agents_module.services.agent_inference_service import AgentInferenceService
from agents_module.services.workflow_inference_service import WorkflowInferenceService
from common_module.common_container import CommonContainer
from agents_module.runtime_config import configure_celery_broker
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.database.connection import DatabaseConfig, DatabaseClient
from db_repo_module.db_repo_container import DatabaseModuleContainer
from flo_cloud.cloud_storage import CloudStorageManager
from guardrails_module.bootstrap import create_guardrails_container_if_enabled
from plugins_module.plugins_container import PluginsContainer
from tools_module.tools_container import ToolsContainer

from celery_worker.settings import CONFIG, CONFIG_INI


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


def get_services() -> WorkerServices:
    global _services
    if _services is not None:
        return _services

    with _lock:
        if _services is not None:
            return _services

        config = CONFIG
        db_client = _build_db_client(config['database'])
        db_repo_container = DatabaseModuleContainer()
        db_repo_container.config.from_ini(CONFIG_INI)
        db_repo_container.db_client.override(providers.Object(db_client))

        common_container = CommonContainer(cache_manager=providers.Object(None))
        common_container.config.from_dict(config)
        runtime = common_container.runtime_settings()
        configure_celery_broker(config['celery']['broker_url'])

        storage = config['storage']

        api_services_container: ApiServicesContainer = create_api_services_container(
            api_service_repository=db_repo_container.api_services_repository,
            cloud_storage_manager=common_container.cloud_storage_manager,
            db_client=db_repo_container.db_client,
            cache_manager=db_repo_container.cache_manager,
            response_formatter=providers.Object(None),
        )

        # Email OAuth/KMS services are not used by this worker (no trigger
        # tasks). Stub kms/oauth so PluginsContainer still constructs for the
        # message-processor repository that agents/tools need.
        plugins_container = PluginsContainer(
            db_client=db_repo_container.db_client,
            cloud_storage_manager=common_container.cloud_storage_manager,
            kms_cipher=providers.Object(None),
            dynamic_query_repository=db_repo_container.dynamic_query_repository,
            cache_manager=db_repo_container.cache_manager,
            oauth_app_repository=providers.Object(None),
            email_connection_repository=db_repo_container.email_connection_repository,
        )
        plugins_container.config.from_dict(config)

        bucket_name = storage['application_bucket']
        if not bucket_name:
            raise ValueError(
                'storage.application_bucket (APPLICATION_BUCKET) must be set in config.ini'
            )
        executions_bucket = bucket_name

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

        llm_inference_config_container = LlmInferenceConfigContainer(
            db_client=db_repo_container.db_client,
            cache_manager=db_repo_container.cache_manager,
            call_processing_cache_invalidator=common_container.call_processing_cache_invalidator,
        )

        guardrails_container = create_guardrails_container_if_enabled(
            config,
            db_client=db_repo_container.db_client,
            cache_manager=db_repo_container.cache_manager,
        )
        guardrails_engine = (
            guardrails_container.guardrails_engine if guardrails_container else None
        )

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
            executions_bucket=executions_bucket,
            llm_inference_config_service=llm_inference_config_container.llm_inference_config_service,
            guardrails_engine=guardrails_engine,
        )
        agents_container.config.from_dict(config)

        _services = WorkerServices(
            agent_inference=agents_container.agent_inference_service(),
            workflow_inference=agents_container.workflow_inference_service(),
            cloud_storage=common_container.cloud_storage_manager(),
            cache=db_repo_container.cache_manager(),
            execution_bucket=executions_bucket,
        )

    return _services
