"""
Initializes all services once per worker process.
No DB connection owned by the worker — status updates go through Redis Streams.
DB credentials are read from env vars so config.ini is not required.
"""

from dotenv import load_dotenv

import os
import threading
from dataclasses import dataclass
from typing import Optional

from dependency_injector import providers

from api_services_module.api_services_container import (
    ApiServicesContainer,
    create_api_services_container,
)
from agents_module.agents_container import AgentsContainer
from agents_module.services.agent_inference_service import AgentInferenceService
from agents_module.services.workflow_inference_service import WorkflowInferenceService
from common_module.common_container import CommonContainer
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.database.connection import DatabaseConfig, DatabaseClient
from db_repo_module.db_repo_container import DatabaseModuleContainer
from flo_cloud.cloud_storage import CloudStorageManager
from plugins_module.plugins_container import PluginsContainer
from tools_module.tools_container import ToolsContainer

load_dotenv()


@dataclass
class WorkerServices:
    agent_inference: AgentInferenceService
    workflow_inference: WorkflowInferenceService
    cloud_storage: CloudStorageManager
    cache: CacheManager
    execution_bucket: str


_lock = threading.Lock()
_services: Optional[WorkerServices] = None


def _build_db_client() -> DatabaseClient:
    """Build DatabaseClient directly from env vars — no config.ini needed."""
    db_config = DatabaseConfig(
        username=os.environ['DB_USERNAME'],
        password=os.environ['DB_PASSWORD'],
        host=os.environ['DB_HOST'],
        port=os.environ['DB_PORT'],
        db_name=os.environ['DB_NAME'],
    )
    return DatabaseClient(db_config)


def get_services() -> WorkerServices:
    global _services
    if _services is not None:
        return _services

    with _lock:
        if _services is not None:
            return _services

        # Build DB client from env vars and override the container's singleton
        db_client = _build_db_client()
        db_repo_container = DatabaseModuleContainer()
        db_repo_container.db_client.override(providers.Object(db_client))

        common_container = CommonContainer(
            cache_manager=db_repo_container.cache_manager
        )

        import google.auth

        _, project = google.auth.default()
        print(
            f"[DEBUG] ADC project: {project}, GOOGLE_CLOUD_PROJECT env: {os.getenv('GOOGLE_CLOUD_PROJECT')}"
        )

        # Override cloud storage manager with env-var-based provider
        cloud_provider = os.environ['CLOUD_PROVIDER']
        common_container.cloud_storage_manager.override(
            providers.Object(CloudStorageManager(provider=cloud_provider))
        )

        api_services_container: ApiServicesContainer = create_api_services_container(
            api_service_repository=db_repo_container.api_services_repository,
            cloud_storage_manager=common_container.cloud_storage_manager,
            db_client=db_repo_container.db_client,
            cache_manager=db_repo_container.cache_manager,
            response_formatter=common_container.response_formatter,
        )

        plugins_container = PluginsContainer(
            db_client=db_repo_container.db_client,
            cloud_storage_manager=common_container.cloud_storage_manager,
            dynamic_query_repository=db_repo_container.dynamic_query_repository,
            cache_manager=db_repo_container.cache_manager,
        )

        bucket_name = os.environ['AGENT_YAML_BUCKET']

        tools_container = ToolsContainer(
            datasource_repository=db_repo_container.datasource_repository,
            knowledge_base_repository=db_repo_container.knowledge_base_repository,
            knowledge_base_inference_repository=db_repo_container.knowledge_base_inference_repository,
            message_processor_repository=plugins_container.message_processor_repository,
            api_services_manager=api_services_container.api_service_manager,
            cloud_storage_manager=common_container.cloud_storage_manager,
            message_processor_bucket_name=bucket_name,
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
            message_processor_repository=plugins_container.message_processor_repository,
            message_processor_bucket_name=bucket_name,
            api_services_manager=api_services_container.api_service_manager,
            async_agentic_execution_repository=db_repo_container.async_agentic_execution_repository,
            executions_bucket=bucket_name,
        )

        # Inject config values from env vars so services like AgentCrudService
        # get the correct bucket_name via config.agents.agent_yaml_bucket
        agents_container.config.from_dict(
            {
                'agents': {'agent_yaml_bucket': bucket_name},
                'cloud_config': {'cloud_provider': os.getenv('CLOUD_PROVIDER', 'aws')},
                'workflow': {'worker_topic': os.getenv('WORKFLOW_WORKER_TOPIC', '')},
            }
        )

        # Must use the same namespace as the floware app so stream keys match
        # floware's CacheManager uses config.env_config.app_name as its namespace
        cache = CacheManager(namespace=os.getenv('APP_NAME', 'floware'))

        _services = WorkerServices(
            agent_inference=agents_container.agent_inference_service(),
            workflow_inference=agents_container.workflow_inference_service(),
            cloud_storage=common_container.cloud_storage_manager(),
            cache=cache,
            execution_bucket=bucket_name,
        )

    return _services
