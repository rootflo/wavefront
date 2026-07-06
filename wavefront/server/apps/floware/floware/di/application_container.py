from dependency_injector import containers
from dependency_injector import providers

from floware.services.notification_service import NotificationService
from floware.services.config_service import ConfigService
from floware.services.scheduled_job_service import ScheduledJobService


class ApplicationContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['./config.ini'])
    # db
    db_client = providers.Dependency()

    email_repository = providers.Dependency()
    oauth_credential_repository = providers.Dependency()
    user_repository = providers.Dependency()
    task_repository = providers.Dependency()

    notification_repository = providers.Dependency()
    notification_user_repository = providers.Dependency()
    config_repository = providers.Dependency()
    cloud_storage_manager = providers.Dependency()
    scheduled_job_repository = providers.Dependency()
    scheduled_job_execution_repository = providers.Dependency()
    datasource_repository = providers.Dependency()
    dynamic_query_repository = providers.Dependency()
    email_service = providers.Dependency()
    user_service = providers.Dependency()
    role_repository = providers.Dependency()
    user_role_repository = providers.Dependency()

    # services
    notification_service = providers.Singleton(
        NotificationService, notification_repository, notification_user_repository
    )

    config_service = providers.Singleton(
        ConfigService,
        config_repository=config_repository,
        cloud_storage_manager=cloud_storage_manager,
        config=config,
    )

    scheduled_job_service = providers.Singleton(
        ScheduledJobService,
        db_client=db_client,
        scheduled_job_repository=scheduled_job_repository,
        scheduled_job_execution_repository=scheduled_job_execution_repository,
        datasource_repository=datasource_repository,
        dynamic_query_repository=dynamic_query_repository,
        cloud_storage_manager=cloud_storage_manager,
        bucket_name=config.floware.asset_storage_bucket,
        email_service=email_service,
        user_repository=user_repository,
        user_service=user_service,
        role_repository=role_repository,
        user_role_repository=user_role_repository,
    )
