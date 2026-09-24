from dependency_injector import containers
from dependency_injector import providers
from gold_module.services.cloud_image_service import AWSImageService
from gold_module.services.cloud_image_service import AzureImageService
from gold_module.services.cloud_image_service import GCPImageService
from gold_module.services.image_service import ImageService


class GoldContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])

    gold_queue = providers.Dependency()

    aws_image_service = providers.Singleton(
        AWSImageService,
        bucket_name=config.storage.application_bucket,
        message_queue=gold_queue,
        region=config.cloud.region,
    )

    gcp_image_service = providers.Singleton(
        GCPImageService,
        bucket_name=config.storage.application_bucket,
        message_queue=gold_queue,
    )

    azure_image_service = providers.Singleton(
        AzureImageService,
        container_name=config.storage.application_bucket,
        account_url=config.azure.account_url,
        message_queue=gold_queue,
    )

    cloud_service = providers.Selector(
        config.cloud.provider,
        aws=aws_image_service,
        gcp=gcp_image_service,
        azure=azure_image_service,
    )

    image_service = providers.Singleton(ImageService, cloud_service=cloud_service)
