"""Dependency injection container for API services module."""

from dependency_injector import containers, providers

from .config.registry import ServiceRegistry
from .config.parser import ServiceDefinitionParser
from .auth.manager import AuthManager
from .core.proxy import ApiProxy
from .core.router import ProxyRouter
from .core.manager import ApiServicesManager
from .pipeline.builder import PipelineBuilder, PipelineCache
from .utils.api_change_processor import ApiChangeProcessor
from .utils.api_change_publisher import ApiChangePublisher


def _initialize_service_registry(service_registry: ServiceRegistry) -> ServiceRegistry:
    """Initialize service registry (without loading from DB - that happens in startup event)."""
    # Don't load from DB here - it's async and container initialization is sync
    # DB loading will happen in the startup event handler
    return service_registry


class ApiServicesContainer(containers.DeclarativeContainer):
    """Dependency injection container for API services module."""

    # Configuration
    config = providers.Configuration()

    # External dependencies (can be injected from parent containers)
    db_client = providers.Dependency()
    cache_manager = providers.Dependency()
    response_formatter = providers.Dependency()

    # api services repository
    api_services_repository = providers.Dependency()

    # cache
    cloud_storage_manager = providers.Dependency()

    # Core service components
    service_definition_parser = providers.Singleton(ServiceDefinitionParser)

    api_service_manager = providers.Singleton(
        ApiServicesManager,
        api_services_repository=api_services_repository,
        cloud_storage_manager=cloud_storage_manager,
        cache_manager=cache_manager,
        config=config,
    )

    api_change_publisher = providers.Singleton(
        ApiChangePublisher,
        cache_manager=cache_manager,
    )

    service_registry = providers.Singleton(
        ServiceRegistry, api_service_manager=api_service_manager
    )

    # Initialize service registry with loaded configurations
    initialized_service_registry = providers.Singleton(
        lambda service_registry: _initialize_service_registry(service_registry),
        service_registry=service_registry,
    )

    auth_manager = providers.Singleton(AuthManager)

    pipeline_builder = providers.Singleton(PipelineBuilder)

    pipeline_cache = providers.Singleton(PipelineCache)

    # Main API proxy (using initialized service registry)
    api_proxy = providers.Singleton(
        ApiProxy,
        service_registry=initialized_service_registry,
        api_services_manager=api_service_manager,
        api_change_publisher=api_change_publisher,
    )

    # Router (using initialized service registry)
    proxy_router = providers.Singleton(
        ProxyRouter,
        proxy=api_proxy,
        service_registry=initialized_service_registry,
        api_services_manager=api_service_manager,
        response_formatter=response_formatter,
    )

    api_change_processor = providers.Singleton(
        ApiChangeProcessor,
        proxy_router=proxy_router,
    )

    # Router factory method
    router = providers.Callable(
        lambda proxy_router: proxy_router.get_router(), proxy_router=proxy_router
    )

    initialized_proxy = providers.Singleton(
        lambda api_proxy, service_registry: api_proxy,
        api_proxy=api_proxy,
        service_registry=initialized_service_registry,
    )


def create_api_services_container(
    api_service_repository,
    cloud_storage_manager,
    response_formatter,
    db_client=None,
    cache_manager=None,
) -> ApiServicesContainer:
    """
    Factory function to create and configure API services container.

    Args:
        api_service_repository: Repository for api service metadata
        cloud_storage_manager: Cloud storage manager for service definitions
        db_client: Database client (optional, for future use)
        cache_manager: Cache manager (optional, for future use)

    Returns:
        Configured ApiServicesContainer
    """
    container = ApiServicesContainer(
        api_services_repository=api_service_repository,
        cloud_storage_manager=cloud_storage_manager,
        response_formatter=response_formatter,
    )

    # Wire external dependencies if provided
    if db_client:
        container.db_client.override(db_client)
    if cache_manager:
        container.cache_manager.override(cache_manager)

    container.wire(
        modules=[__name__],
        packages=[
            'api_services_module.execution',
        ],
    )

    return container
