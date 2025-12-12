import os

from dependency_injector import containers
from dependency_injector import providers
from gold_module.services.cloud_image_service import AWSImageService
from gold_module.services.cloud_image_service import GCPImageService
from gold_module.services.image_service import ImageService


class GoldContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])

    cloud_provider = providers.Singleton(
        lambda: os.environ.get('CLOUD_PROVIDER', 'gcp').lower()
    )

    aws_image_service = providers.Singleton(
        AWSImageService,
        bucket_name=config.aws.aws_asset_storage_bucket,
        queue_url=config.aws.queue_url,
        region=config.aws.region,
    )

    gcp_image_service = providers.Singleton(
        GCPImageService,
        bucket_name=config.gcp.gcp_asset_storage_bucket,
        project_id=config.gcp.gcp_project_id,
        topic_id=config.gcp.gold_topic_id,
    )

    # provider.selector is basically an if/else. if cloud_provider = gcp, gcp_image_service will be selected
    cloud_service = providers.Selector(
        cloud_provider, aws=aws_image_service, gcp=gcp_image_service
    )

    image_service = providers.Singleton(ImageService, cloud_service=cloud_service)
