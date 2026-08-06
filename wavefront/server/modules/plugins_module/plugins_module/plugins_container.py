from dependency_injector import containers
from dependency_injector import providers
from db_repo_module.models.datasource import Datasource
from db_repo_module.models.authenticator import Authenticator
from db_repo_module.models.message_processors import MessageProcessors
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from plugins_module.services.configuration_service import ConfigurationService
from plugins_module.services.dynamic_query_service import DynamicQueryService
from plugins_module.services.message_processor_service import MessageProcessorService
from flo_cloud.cloud_storage import CloudStorageManager


class PluginsContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])

    db_client = providers.Dependency()

    cache_manager = providers.Dependency()

    dynamic_query_repository = providers.Dependency()

    # Injected from db_repo_container rather than declared here: the namespace
    # repository already exists there, and the configuration store only needs it
    # to check that a namespace exists before writing to it.
    agentic_configuration_repository = providers.Dependency()

    namespace_repository = providers.Dependency()

    datasource_repository = providers.Singleton(
        SQLAlchemyRepository[Datasource],
        model=Datasource,
        db_client=db_client,
    )

    authenticator_repository = providers.Singleton(
        SQLAlchemyRepository[Authenticator],
        model=Authenticator,
        db_client=db_client,
    )

    message_processor_repository = providers.Singleton(
        SQLAlchemyRepository[MessageProcessors],
        model=MessageProcessors,
        db_client=db_client,
    )

    # dynamic query service
    cloud_provider = config.cloud_config.cloud_provider

    cloud_storage_manager = providers.Singleton(
        CloudStorageManager, provider=config.cloud_config.cloud_provider
    )

    dynamic_query_service = providers.Singleton(
        DynamicQueryService,
        cloud_storage_manager=cloud_storage_manager,
        dynamic_query_repo=dynamic_query_repository,
        bucket_name=config.floware.asset_storage_bucket,
    )

    configuration_service = providers.Singleton(
        ConfigurationService,
        configuration_repository=agentic_configuration_repository,
        namespace_repository=namespace_repository,
        cache_manager=cache_manager,
    )

    message_processor_service = providers.Singleton(
        MessageProcessorService,
        cloud_storage_manager=cloud_storage_manager,
        message_processor_repository=message_processor_repository,
        hermes_url=config.hermes.url,
        bucket_name=config.floware.asset_storage_bucket,
    )
