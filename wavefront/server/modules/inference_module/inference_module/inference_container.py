from db_repo_module.models.model_schema import ModelSchema
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector import containers
from dependency_injector import providers
from flo_cloud.cloud_storage import CloudStorageManager


class InferenceContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])
    db_client = providers.Dependency()
    cache_manager = providers.Dependency()
    model_inference_repository = providers.Singleton(
        SQLAlchemyRepository[ModelSchema],
        model=ModelSchema,
        db_client=db_client,
    )

    cloud_storage_manager = providers.Singleton(
        CloudStorageManager, provider=config.cloud_config.cloud_provider
    )
