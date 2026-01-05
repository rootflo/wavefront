from common_module.response_formatter import ResponseFormatter
from common_module.scheduler import Scheduler
from dependency_injector import containers
from dependency_injector import providers

from flo_cloud.cloud_storage import CloudStorageManager


class CommonContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['./config.ini'])

    response_formatter = providers.Singleton(ResponseFormatter)

    cache_manager = providers.Dependency()

    # periodic scheduler
    scheduler = providers.Singleton(
        Scheduler,
        redis_host=config.redis.host,
        redis_port=config.redis.port,
        cache_manager=cache_manager,
    )

    cloud_storage_manager = providers.Singleton(
        CloudStorageManager, provider=config.cloud_config.cloud_provider
    )
