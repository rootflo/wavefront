from dependency_injector import containers
from dependency_injector import providers
from agents_module.services.agent_inference_service import AgentInferenceService
from agents_module.services.agent_crud_service import AgentCrudService
from agents_module.services.namespace_service import NamespaceService
from agents_module.services.workflow_crud_service import WorkflowCrudService
from agents_module.services.workflow_inference_service import WorkflowInferenceService
from flo_cloud.message_queue import MessageQueueManager


class AgentsContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])

    db_client = providers.Dependency()

    cloud_storage_manager = providers.Dependency()

    cache_manager = providers.Dependency()

    tool_loader = providers.Dependency()

    workflow_pipeline_repository = providers.Dependency()
    workflow_runs_repository = providers.Dependency()

    namespace_repository = providers.Dependency()

    agent_repository = providers.Dependency()

    workflow_repository = providers.Dependency()

    namespace_service = providers.Singleton(
        NamespaceService,
        namespace_repository=namespace_repository,
        cache_manager=cache_manager,
    )

    agent_crud_service = providers.Singleton(
        AgentCrudService,
        agent_repository=agent_repository,
        namespace_service=namespace_service,
        cloud_storage_manager=cloud_storage_manager,
        cache_manager=cache_manager,
        bucket_name=config.agents.agent_yaml_bucket,
    )

    # Agent inference service
    agent_inference_service = providers.Singleton(
        AgentInferenceService,
        cache_manager=cache_manager,
        tool_loader=tool_loader,
        agent_crud_service=agent_crud_service,
    )

    workflow_crud_service = providers.Singleton(
        WorkflowCrudService,
        workflow_repository=workflow_repository,
        namespace_service=namespace_service,
        cloud_storage_manager=cloud_storage_manager,
        cache_manager=cache_manager,
        bucket_name=config.agents.agent_yaml_bucket,
        agent_crud_service=agent_crud_service,
        tool_loader=tool_loader,
    )

    workflow_inference_service = providers.Singleton(
        WorkflowInferenceService,
        cloud_storage_manager=cloud_storage_manager,
        cache_manager=cache_manager,
        bucket_name=config.agents.agent_yaml_bucket,
        agent_crud_service=agent_crud_service,
        tool_loader=tool_loader,
    )

    message_queue_manager = providers.Singleton(
        MessageQueueManager,
        cloud_provider=config.cloud_config.cloud_provider,
    )
