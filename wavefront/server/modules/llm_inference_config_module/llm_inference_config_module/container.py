from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector import containers
from dependency_injector import providers
from llm_inference_config_module.services.inference_proxy_service import (
    InferenceProxyService,
)
from llm_inference_config_module.services.llm_inference_config_service import (
    LlmInferenceConfigService,
)


class LlmInferenceConfigContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])

    # External dependencies
    db_client = providers.Dependency()
    cache_manager = providers.Dependency()

    # Repository
    llm_inference_config_repository = providers.Singleton(
        SQLAlchemyRepository[LlmInferenceConfig],
        model=LlmInferenceConfig,
        db_client=db_client,
    )

    # Services
    llm_inference_config_service = providers.Singleton(
        LlmInferenceConfigService,
        llm_inference_config_repository=llm_inference_config_repository,
        cache_manager=cache_manager,
    )

    inference_proxy_service = providers.Singleton(
        InferenceProxyService,
        llm_inference_config_service=llm_inference_config_service,
    )
