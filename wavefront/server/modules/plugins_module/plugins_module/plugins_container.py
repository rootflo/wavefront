from dependency_injector import containers
from dependency_injector import providers
from db_repo_module.models.datasource import Datasource
from db_repo_module.models.authenticator import Authenticator
from db_repo_module.models.message_processors import MessageProcessors
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from plugins_module.services.dynamic_query_service import DynamicQueryService
from plugins_module.services.message_processor_service import MessageProcessorService
from flo_cloud.cloud_storage import CloudStorageManager


class PluginsContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])

    db_client = providers.Dependency()

    cache_manager = providers.Dependency()

    dynamic_query_repository = providers.Dependency()

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

    cloud_manager = providers.Singleton(
        CloudStorageManager, provider=config.cloud_config.cloud_provider
    )

    dynamic_query_service = providers.Singleton(
        DynamicQueryService,
        cloud_manager=cloud_manager,
        dynamic_query_repo=dynamic_query_repository,
        bucket_name=config.aws.aws_asset_storage_bucket
        if cloud_provider == 'aws'
        else config.gcp.gcp_asset_storage_bucket,
    )

    message_processor_service = providers.Singleton(
        MessageProcessorService,
        cloud_manager=cloud_manager,
        message_processor_repository=message_processor_repository,
        bucket_name=config.aws.aws_asset_storage_bucket
        if cloud_provider == 'aws'
        else config.gcp.gcp_asset_storage_bucket,
        hermes_url=config.hermes.url,
    )
