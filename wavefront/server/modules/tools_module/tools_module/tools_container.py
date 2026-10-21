from dependency_injector import containers
from dependency_injector import providers
from tools_module.registry.tool_loader import ToolLoader
from tools_module.services.tool_service import ToolService
from tools_module.floware_api import FlowareApiClient
from tools_module.registry.function_registry import build_function_registry

from tools_module.datasources.provider import DatasourceToolDetailsProvider
from tools_module.email.provider import EmailToolDetailsProvider
from tools_module.message_processor.provider import MessageProcessorToolDetailsProvider
from tools_module.api_service.provider import ApiServiceToolDetailsProvider
from tools_module.services.default_tool_provider import DefaultToolDetailsProvider


class ToolsContainer(containers.DeclarativeContainer):
    """Dependency injection container for tools module"""

    datasource_repository = providers.Dependency()
    email_connection_repository = providers.Dependency()
    message_processor_repository = providers.Dependency()
    api_services_manager = providers.Dependency()
    cloud_storage_manager = providers.Dependency()
    message_processor_bucket_name = providers.Dependency()
    floware_base_url = providers.Dependency()
    passthrough_secret = providers.Dependency()

    # Tools that call floware's REST API get this client bound as their first
    # argument, so they hold no settings of their own.
    floware_api = providers.Singleton(
        FlowareApiClient,
        base_url=floware_base_url,
        passthrough_secret=passthrough_secret,
    )

    function_registry = providers.Singleton(build_function_registry, api=floware_api)

    tool_loader = providers.Singleton(
        ToolLoader,
        function_registry=function_registry,
        tools_json_path=None,
    )

    # Tool Providers
    datasource_tool_provider = providers.Singleton(
        DatasourceToolDetailsProvider, datasource_repository=datasource_repository
    )

    email_tool_provider = providers.Singleton(
        EmailToolDetailsProvider,
        email_connection_repository=email_connection_repository,
    )

    message_processor_tool_provider = providers.Singleton(
        MessageProcessorToolDetailsProvider,
        message_processor_repository=message_processor_repository,
        cloud_storage_manager=cloud_storage_manager,
        message_processor_bucket_name=message_processor_bucket_name,
    )

    api_service_tool_provider = providers.Singleton(
        ApiServiceToolDetailsProvider,
        api_services_manager=api_services_manager,
    )

    default_tool_provider = providers.Singleton(DefaultToolDetailsProvider)

    # Tool service
    tool_service = providers.Singleton(
        ToolService,
        tool_loader=tool_loader,
        tool_providers=providers.List(
            datasource_tool_provider,
            email_tool_provider,
            message_processor_tool_provider,
            api_service_tool_provider,
            default_tool_provider,
        ),
    )
