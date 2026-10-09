"""Floware's application DI container.

One strict read of config.ini. Module containers are children and receive that
config; they do not open the file themselves. Process-wide side effects
(logging, telemetry, the Presidio regex timeout) run from ``init_resources``.
"""

from __future__ import annotations

from pathlib import Path

from agents_module.agents_container import AgentsContainer
from api_services_module.api_services_container import ApiServicesContainer
from auth_module.auth_container import AuthContainer
from chatbots_module.chatbots_container import ChatbotsContainer
from common_module.common_container import CommonContainer
from common_module.config_loader import load_ini
from db_repo_module.db_repo_container import DatabaseModuleContainer
from dependency_injector import containers
from dependency_injector import providers
from floware.di.helpers import (
    guardrails_engine,
    guardrails_mode,
    scheduler_worker_id,
    start_logging,
    start_presidio_timeout,
    start_telemetry,
)
from floware.repositories.config_repository import AppConfigRepository
from floware.repositories.datasource_repository import AppDatasourceRepository
from floware.repositories.knowledge_base_repository import AppKnowledgeBaseRepository
from floware.services.config_service import ConfigService
from floware.services.notification_service import NotificationService
from floware.services.scheduled_job_service import ScheduledJobService
from floware.services.scheduler_manager import SchedulerManager
from gold_module.gold_container import GoldContainer
from guardrails_module.container import GuardrailsContainer
from knowledge_base_module.knowledge_base_container import KnowledgeBaseContainer
from llm_inference_config_module.container import LlmInferenceConfigContainer
from plugins_module.plugins_container import PluginsContainer
from product_analysis_module.product_analysis_container import ProductAnalysisContainer
from tools_module.tools_container import ToolsContainer
from user_management_module.user_container import UserContainer
from voice_agents_module.voice_agents_container import VoiceAgentsContainer

CONFIG_INI = Path(__file__).resolve().parent.parent / 'config.ini'


class ApplicationContainer(containers.DeclarativeContainer):
    config = providers.Configuration(strict=True)

    logging = providers.Resource(
        start_logging,
        app_name=config.env_config.app_name,
        log_level=config.env_config.log_level,
    )
    telemetry = providers.Resource(start_telemetry, config)
    presidio_regex_timeout = providers.Resource(
        start_presidio_timeout,
        timeout=config.guardrails.regex_timeout_seconds,
    )

    db = providers.Container(DatabaseModuleContainer, config=config)
    common = providers.Container(
        CommonContainer,
        config=config,
        cache_manager=db.cache_manager,
    )

    guardrails = providers.Selector(
        providers.Callable(guardrails_mode, config.guardrails.enabled),
        on=providers.Container(
            GuardrailsContainer,
            config=config,
            db_client=db.db_client,
            cache_manager=db.cache_manager,
        ),
        off=providers.Object(None),
    )

    auth = providers.Container(
        AuthContainer,
        config=config,
        db_client=db.db_client,
        cache_manager=db.cache_manager,
        kms_signer=common.kms_signer,
    )

    plugins = providers.Container(
        PluginsContainer,
        config=config,
        db_client=db.db_client,
        cloud_storage_manager=common.cloud_storage_manager,
        kms_cipher=common.kms_cipher,
        dynamic_query_repository=db.dynamic_query_repository,
        cache_manager=db.cache_manager,
        namespace_repository=db.namespace_repository,
        agentic_configuration_repository=db.agentic_configuration_repository,
        datasource_audit_log_repository=db.datasource_audit_log_repository,
        notification_repository=db.notification_repository,
        oauth_app_repository=db.oauth_app_repository,
        email_connection_repository=db.email_connection_repository,
        feature_flags=common.feature_flags,
    )

    user = providers.Container(
        UserContainer,
        config=config,
        db_client=db.db_client,
        cache_manager=db.cache_manager,
        email_send_service=plugins.email_send_service,
    )

    knowledge_base = providers.Container(
        KnowledgeBaseContainer,
        config=config,
        db_client=db.db_client,
        ingestion_db_client=db.ingestion_db_client,
        cache_manager=db.cache_manager,
        cloud_storage_manager=common.cloud_storage_manager,
        rag_queue=common.rag_queue,
    )

    gold = providers.Container(
        GoldContainer,
        config=config,
        cloud_storage_manager=common.cloud_storage_manager,
        gold_queue=common.gold_queue,
    )

    product_analysis = providers.Container(ProductAnalysisContainer, config=config)

    api_services = providers.Container(
        ApiServicesContainer,
        config=config,
        api_services_repository=db.api_services_repository,
        cloud_storage_manager=common.cloud_storage_manager,
        db_client=db.db_client,
        cache_manager=db.cache_manager,
        response_formatter=common.response_formatter,
    )

    tools = providers.Container(
        ToolsContainer,
        datasource_repository=db.datasource_repository,
        email_connection_repository=db.email_connection_repository,
        message_processor_repository=plugins.message_processor_repository,
        api_services_manager=api_services.api_service_manager,
        cloud_storage_manager=common.cloud_storage_manager,
        message_processor_bucket_name=config.storage.application_bucket,
        floware_base_url=common.runtime_settings.provided.floware_base_url,
        passthrough_secret=common.runtime_settings.provided.passthrough_secret,
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
        guardrails_engine=providers.Callable(guardrails_engine, guardrails),
    )

    voice_agents = providers.Container(
        VoiceAgentsContainer,
        config=config,
        db_client=db.db_client,
        cache_manager=db.cache_manager,
        cloud_storage_manager=common.cloud_storage_manager,
        call_processing_cache_invalidator=common.call_processing_cache_invalidator,
    )

    chatbots = providers.Container(
        ChatbotsContainer,
        config=config,
        db_client=db.db_client,
        cache_manager=db.cache_manager,
        llm_inference_config_service=llm_inference_config.llm_inference_config_service,
        guardrails_engine=providers.Callable(guardrails_engine, guardrails),
    )

    scheduler_manager = providers.Singleton(SchedulerManager)

    app_config_repository = providers.Singleton(
        AppConfigRepository,
        repository=db.config_repository,
        cache_manager=db.cache_manager,
    )
    app_datasource_repository = providers.Singleton(
        AppDatasourceRepository,
        repository=db.datasource_repository,
        cache_manager=db.cache_manager,
    )
    app_knowledge_base_repository = providers.Singleton(
        AppKnowledgeBaseRepository,
        repository=db.knowledge_base_repository,
        cache_manager=db.cache_manager,
    )

    notification_service = providers.Singleton(
        NotificationService,
        notification_repository=db.notification_repository,
        notification_user_repository=db.notification_user_repository,
    )

    config_service = providers.Singleton(
        ConfigService,
        app_config_repository=app_config_repository,
        datasource_repository=app_datasource_repository,
        knowledge_base_repository=app_knowledge_base_repository,
        cloud_storage_manager=common.cloud_storage_manager,
        config=config,
    )

    scheduled_job_service = providers.Singleton(
        ScheduledJobService,
        db_client=db.db_client,
        scheduled_job_repository=db.scheduled_job_repository,
        scheduled_job_execution_repository=db.scheduled_job_execution_repository,
        datasource_repository=db.datasource_repository,
        dynamic_query_repository=db.dynamic_query_repository,
        cloud_storage_manager=common.cloud_storage_manager,
        bucket_name=config.storage.application_bucket,
        email_send_service=plugins.email_send_service,
        email_connection_service=plugins.email_connection_service,
        user_repository=db.user_repository,
        user_service=user.user_service,
        role_repository=user.role_repository,
        user_role_repository=user.user_role_repository,
        worker_id=providers.Callable(scheduler_worker_id, config.scheduler.worker_id),
    )


def create_container() -> ApplicationContainer:
    container = ApplicationContainer()
    load_ini(container.config, CONFIG_INI)
    container.init_resources()
    return container
