import os

from dependency_injector import containers
from dependency_injector import providers
from insights_module.db.bigquery_connector import BigQueryConfig
from insights_module.db.bigquery_connector import BigQueryConnector
from insights_module.db.redshift_connector import RedshiftConfig
from insights_module.db.redshift_connector import RedshiftConnector
from insights_module.repository.pvo_repository import PVORepository
from insights_module.service.dynamic_query_service import DynamicQueryService
from insights_module.service.insights_service import InsightsService
from insights_module.service.pdo_service import AWSServices
from insights_module.service.pdo_service import GCPServices
from insights_module.service.usage_metric_service import UsageMetricService
from flo_cloud.cloud_storage import CloudStorageManager


class InsightsContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['./config.ini'])

    notification_repository = providers.Dependency()

    cache_manager = providers.Dependency()

    cloud_provider = os.environ.get('CLOUD_PROVIDER', 'aws')

    if cloud_provider == 'aws':
        redshift_config = providers.Factory(
            RedshiftConfig,
            username=config.redshift.username,
            password=config.redshift.password,
            host=config.redshift.host,
            port=config.redshift.port,
            db_name=config.redshift.db_name,
        )
        connector = providers.Singleton(RedshiftConnector, redshift_config)
    elif cloud_provider == 'gcp':
        bq_config = providers.Factory(
            BigQueryConfig,
            project_id=config.bigquery.project_id,
            dataset_id=config.bigquery.dataset_id,
        )
        connector = providers.Singleton(BigQueryConnector, bq_config)

    pvo_repository = providers.Singleton(
        PVORepository,
        connector,
        dataset_id=config.bigquery.dataset_id,
    )

    insights_service = providers.Singleton(
        InsightsService,
        repository=pvo_repository,
        today_as_max_from_db=config.insights.today_as_max_from_db,
    )
    usage_metric_service = providers.Singleton(
        UsageMetricService,
        repository=pvo_repository,
        cloud_provider=cloud_provider,
    )

    if cloud_provider == 'aws':
        cloud_service = providers.Singleton(
            AWSServices,
            insights_service=insights_service,
            transcript_bucket_name=config.aws.transcript_bucket_name,
            audio_bucket_name=config.aws.audio_bucket_name,
        )
    elif cloud_provider == 'gcp':
        cloud_service = providers.Singleton(
            GCPServices,
            insights_service=insights_service,
            transcript_bucket_name=config.gcp.transcript_bucket_name,
            audio_bucket_name=config.gcp.audio_bucket_name,
        )

    colud_manager = providers.Singleton(
        CloudStorageManager, provider=config.cloud_config.cloud_provider
    )
    dynamic_query_service = providers.Singleton(
        DynamicQueryService,
        pvo_repository=pvo_repository,
        cache_manager=cache_manager,
    )
