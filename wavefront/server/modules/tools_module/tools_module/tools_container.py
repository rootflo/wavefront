from dependency_injector import containers
from dependency_injector import providers
from tools_module.registry.tool_loader import ToolLoader
from tools_module.services.tool_service import ToolService


from tools_module.datasources.provider import DatasourceToolDetailsProvider
from tools_module.knowlegebase.provider import KnowledgeBaseToolDetailsProvider
from tools_module.services.default_tool_provider import DefaultToolDetailsProvider


class ToolsContainer(containers.DeclarativeContainer):
    """Dependency injection container for tools module"""

    datasource_repository = providers.Dependency()
    knowledge_base_repository = providers.Dependency()
    knowledge_base_inference_repository = providers.Dependency()
    # Tool loader
    tool_loader = providers.Singleton(
        ToolLoader,
        tools_json_path=None,  # Uses default path
    )

    # Tool Providers
    datasource_tool_provider = providers.Singleton(
        DatasourceToolDetailsProvider, datasource_repository=datasource_repository
    )

    knowledge_base_tool_provider = providers.Singleton(
        KnowledgeBaseToolDetailsProvider,
        knowledge_base_repository=knowledge_base_repository,
        knowledge_base_inference_repository=knowledge_base_inference_repository,
    )

    default_tool_provider = providers.Singleton(DefaultToolDetailsProvider)

    # Tool service
    tool_service = providers.Singleton(
        ToolService,
        tool_loader=tool_loader,
        tool_providers=providers.List(
            datasource_tool_provider,
            knowledge_base_tool_provider,
            default_tool_provider,
        ),
    )
