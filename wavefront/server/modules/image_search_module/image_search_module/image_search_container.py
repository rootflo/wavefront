from dependency_injector import containers, providers
from image_search_module.services.image_matching_service import ImageMatchingService
from image_search_module.services.reference_image_service import ReferenceImageService
from image_search_module.services.algorithm_factory import AlgorithmFactory
from image_search_module.services.algorithm_service import AlgorithmService
from image_search_module.services.ikb_service import IKBService
from image_search_module.algorithms.base import AlgorithmType
from image_search_module.repositories.sift_features_repository import (
    SIFTFeaturesRepository,
)
from db_repo_module.models.image_search_models import (
    ReferenceImageFeatures,
    SIFTFeatures,
)
from db_repo_module.models.ikb_models import ImageKnowledgeBase
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from image_search_module.repositories.ikb_repository import IKBRepository
import os
import yaml


class ImageSearchContainer(containers.DeclarativeContainer):
    """Dependency injection container for image search module"""

    _container_dir = os.path.dirname(os.path.abspath(__file__))
    _config_path = os.path.join(_container_dir, 'config', 'algorithm_configs.yaml')

    with open(_config_path, 'r') as file:
        config = yaml.safe_load(file)

    cloud_configs = providers.Configuration(ini_files=['config.ini'])

    cloud_storage_manager = providers.Dependency()

    db_client = providers.Dependency()

    active_algorithm_type = providers.Factory(
        AlgorithmType, config['service']['active_algorithm']
    )

    reference_features_repository = providers.Singleton(
        SQLAlchemyRepository[ReferenceImageFeatures],
        model=ReferenceImageFeatures,
        db_client=db_client,
    )

    ikb_repository_db = providers.Singleton(
        SQLAlchemyRepository[ImageKnowledgeBase],
        model=ImageKnowledgeBase,
        db_client=db_client,
    )

    ikb_repository = providers.Singleton(
        IKBRepository,
        db_repository=ikb_repository_db,
    )

    sift_features_repository = providers.Singleton(
        SIFTFeaturesRepository,
        model=SIFTFeatures,
        db_client=db_client,
    )

    # Core services
    algorithm_factory = providers.Singleton(AlgorithmFactory)

    algorithm_service = providers.Singleton(
        AlgorithmService, algorithm_factory=algorithm_factory
    )

    reference_image_service = providers.Singleton(
        ReferenceImageService,
        features_repository=reference_features_repository,
        sift_features_repository=sift_features_repository,
        algorithm_service=algorithm_service,
        cloud_storage_manager=cloud_storage_manager,
        bucket_name=cloud_configs.image_search.reference_images_bucket,
    )

    # Main image matching service
    image_matching_service = providers.Singleton(
        ImageMatchingService,
        algorithm_factory=algorithm_factory,
        reference_service=reference_image_service,
        active_algorithm_type=active_algorithm_type,
        algorithm_config=config['algorithms'],
        max_results=config['service']['max_results'],
    )

    # IKB service
    ikb_service = providers.Singleton(
        IKBService,
        image_matching_service=image_matching_service,
        reference_image_service=reference_image_service,
        ikb_repository=ikb_repository,
    )
