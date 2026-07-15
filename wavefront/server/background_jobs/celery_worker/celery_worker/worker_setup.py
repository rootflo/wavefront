"""
Initializes all services once per worker process.
No DB connection owned by the worker — status updates go through Redis Streams.
DB credentials are read from env vars so config.ini is not required.
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
from agents_module.services.agent_inference_service import AgentInferenceService
from agents_module.services.workflow_inference_service import WorkflowInferenceService
from common_module.common_container import CommonContainer
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.database.connection import DatabaseConfig, DatabaseClient
from db_repo_module.db_repo_container import DatabaseModuleContainer
from flo_cloud.cloud_storage import CloudStorageManager
from plugins_module.plugins_container import PluginsContainer
from tools_module.tools_container import ToolsContainer
from triggers_module.services.trigger_event_processor import TriggerEventProcessor
from triggers_module.triggers_container import TriggersContainer

from celery_worker.env import (
    AGENT_YAML_BUCKET,
    AGENTIC_EXECUTIONS_BUCKET,
    APP_NAME,
    CLOUD_PROVIDER,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USERNAME,
    GCP_PROJECT_ID,
    GMAIL_PUBSUB_OIDC_SA_EMAIL,
    GMAIL_PUBSUB_TOPIC_PREFIX,
    GMAIL_PUSH_ENDPOINT_TEMPLATE,
    GOOGLE_OAUTH_CLIENT_ID,
    GOOGLE_OAUTH_CLIENT_SECRET,
    GOOGLE_OAUTH_REDIRECT_URI,
    WORKFLOW_WORKER_TOPIC,
)


@dataclass
class WorkerServices:
    agent_inference: AgentInferenceService
    workflow_inference: WorkflowInferenceService
    cloud_storage: CloudStorageManager
    cache: CacheManager
    execution_bucket: str
    trigger_event_processor: TriggerEventProcessor


_lock = threading.Lock()
_services: Optional[WorkerServices] = None


def _build_db_client() -> DatabaseClient:
    """Build DatabaseClient directly from env vars — no config.ini needed."""
    db_config = DatabaseConfig(
        username=DB_USERNAME,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        db_name=DB_NAME,
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

        # Override cloud storage manager with env-var-based provider
        common_container.cloud_storage_manager.override(
            providers.Object(CloudStorageManager(provider=CLOUD_PROVIDER))
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

        bucket_name = AGENT_YAML_BUCKET

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
            agent_version_repository=db_repo_container.agent_version_repository,
            workflow_repository=db_repo_container.workflow_repository,
            workflow_version_repository=db_repo_container.workflow_version_repository,
            message_processor_repository=plugins_container.message_processor_repository,
            message_processor_bucket_name=bucket_name,
            api_services_manager=api_services_container.api_service_manager,
            async_agentic_execution_repository=db_repo_container.async_agentic_execution_repository,
            executions_bucket=AGENTIC_EXECUTIONS_BUCKET,
        )

        # Inject config values from env vars so services like AgentCrudService
        # get the correct bucket_name via config.agents.agent_yaml_bucket
        agents_container.config.from_dict(
            {
                'agents': {'agent_yaml_bucket': bucket_name},
                'cloud_config': {'cloud_provider': CLOUD_PROVIDER},
                'workflow': {'worker_topic': WORKFLOW_WORKER_TOPIC},
            }
        )

        # Must use the same namespace as the floware app so stream keys match
        # floware's CacheManager uses config.env_config.app_name as its namespace
        cache = CacheManager(namespace=APP_NAME)

        triggers_container = TriggersContainer(
            trigger_repository=db_repo_container.agentic_trigger_repository,
            credential_repository=db_repo_container.agentic_trigger_credential_repository,
            event_repository=db_repo_container.agentic_trigger_event_repository,
            agent_repository=db_repo_container.agent_repository,
            workflow_repository=db_repo_container.workflow_repository,
            async_agentic_execution_service=agents_container.async_agentic_execution_service,
        )
        triggers_container.config.from_dict(
            {
                'cloud_config': {'cloud_provider': CLOUD_PROVIDER},
                'triggers_gmail': {
                    'client_id': GOOGLE_OAUTH_CLIENT_ID,
                    'client_secret': GOOGLE_OAUTH_CLIENT_SECRET,
                    'redirect_uri': GOOGLE_OAUTH_REDIRECT_URI,
                    'pubsub_project_id': GCP_PROJECT_ID,
                    'pubsub_topic_prefix': GMAIL_PUBSUB_TOPIC_PREFIX,
                    'push_endpoint_template': GMAIL_PUSH_ENDPOINT_TEMPLATE,
                    'oidc_service_account_email': GMAIL_PUBSUB_OIDC_SA_EMAIL or None,
                },
            }
        )

        _services = WorkerServices(
            agent_inference=agents_container.agent_inference_service(),
            workflow_inference=agents_container.workflow_inference_service(),
            cloud_storage=common_container.cloud_storage_manager(),
            cache=cache,
            execution_bucket=AGENTIC_EXECUTIONS_BUCKET,
            trigger_event_processor=triggers_container.trigger_event_processor(),
        )

    return _services
