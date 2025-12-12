from dependency_injector import containers
from dependency_injector import providers

from floware.services.notification_service import NotificationService
from flo_cloud.cloud_storage import CloudStorageManager
from floware.services.config_service import ConfigService


class ApplicationContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['./config.ini'])
    # db
    db_client = providers.Dependency()

    email_repository = providers.Dependency()
    oauth_credential_repository = providers.Dependency()
    user_repository = providers.Dependency()
    task_repository = providers.Dependency()

    insights_service = providers.Dependency()
    pvo_repository = providers.Dependency()

    notification_repository = providers.Dependency()
    notification_user_repository = providers.Dependency()
    config_repository = providers.Dependency()

    # services
    notification_service = providers.Singleton(
        NotificationService, notification_repository, notification_user_repository
    )

    cloud_manager = providers.Singleton(
        CloudStorageManager,
        provider=config.cloud_config.cloud_provider,
    )

    config_service = providers.Singleton(
        ConfigService,
        config_repository=config_repository,
        cloud_manager=cloud_manager,
        config=config,
    )
