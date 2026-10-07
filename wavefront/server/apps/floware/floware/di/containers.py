"""Build and export all floware DI containers and process-level config side effects.

Feature flags must be applied before ``AuthContainer`` is imported: that container
adds ``superset_service`` only when ``SUPERSET_FLAG`` is already true at class
definition time, and ``superset_controller`` always references it.
"""

from agents_module.runtime_config import (
    configure_azure_openai_api_version,
    configure_celery_broker,
)
from common_module.common_container import CommonContainer
from common_module.feature.feature_flag import configure_feature_flags
from common_module.log.logger import configure_logging
from common_module.utils.odata_settings import configure_odata_cloud_provider
from db_repo_module.db_repo_container import DatabaseModuleContainer
from floware.di.application_container import ApplicationContainer
from floware.services.scheduler_manager import SchedulerManager


def csv(value: str | None, default: tuple[str, ...] = ()) -> list[str]:
    """Split a comma-separated config value; ``default`` when it is not set."""
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(',') if item.strip()]


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
    log_level=config['env_config']['log_level'],
)

# ruff: noqa: E402
# require_auth imports AuthContainer; both must load after feature flags so
# SUPERSET_FLAG can gate AuthContainer.superset_service at class definition.
from user_management_module.authorization.require_auth import (
    configure_jwt_auth_settings,
)

configure_jwt_auth_settings(
    validation_issuer=config['jwt_token']['validation_issuer'],
    audience=config['jwt_token']['audience'],
    token_prefix=config['jwt_token']['console_token_prefix'],
)

from agents_module.agents_container import AgentsContainer
from api_services_module.api_services_container import ApiServicesContainer
from api_services_module.api_services_container import create_api_services_container
from auth_module.auth_container import AuthContainer
from chatbots_module.chatbots_container import ChatbotsContainer
from gold_module.gold_container import GoldContainer
from guardrails_module.bootstrap import create_guardrails_container_if_enabled
from knowledge_base_module.knowledge_base_container import KnowledgeBaseContainer
from llm_inference_config_module.container import LlmInferenceConfigContainer
from plugins_module.plugins_container import PluginsContainer
from product_analysis_module.product_analysis_container import ProductAnalysisContainer
from tools_module.tools_container import ToolsContainer
from user_management_module.user_container import UserContainer
from voice_agents_module.voice_agents_container import VoiceAgentsContainer

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

llm_inference_config_container = LlmInferenceConfigContainer(
    db_client=db_repo_container.db_client,
    cache_manager=db_repo_container.cache_manager,
    call_processing_cache_invalidator=common_container.call_processing_cache_invalidator,
)

# Built only when [guardrails] enabled=true — keeps the engine out of the
# process when the feature is off.
guardrails_container = create_guardrails_container_if_enabled(
    config,
    db_client=db_repo_container.db_client,
    cache_manager=db_repo_container.cache_manager,
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
    executions_bucket=config['storage']['application_bucket'],
    llm_inference_config_service=llm_inference_config_container.llm_inference_config_service,
    guardrails_engine=(
        guardrails_container.guardrails_engine if guardrails_container else None
    ),
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
