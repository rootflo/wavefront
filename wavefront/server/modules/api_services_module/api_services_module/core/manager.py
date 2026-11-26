from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.api_services import ApiServices
from flo_cloud.cloud_storage import CloudStorageManager
from typing import List
from common_module.blocking_io import BlockingPoolBusyError, Pool, run_in_pool
from common_module.log.logger import logger


# Same TTL the definition cache had before (CacheManager's add default).
_DEFINITION_CACHE_SECONDS = 3600


class ApiServicesManager:
    """Manager for API services."""

    def __init__(
        self,
        api_services_repository: SQLAlchemyRepository[ApiServices],
        cloud_storage_manager: CloudStorageManager,
        cache_manager: CacheManager,
        config: dict,
    ):
        """Initialize the API services manager."""
        self.config = config
        self.cache_manager = cache_manager
        self.api_services_repository = api_services_repository
        self.cloud_storage_manager = cloud_storage_manager
        self.application_bucket = config['storage']['application_bucket']

    async def create_api_service(
        self, id: str, service_def_yaml: str
    ) -> ApiServices | None:
        """Create a new API service."""
        service_def_path = f'api_services/{id}.yaml'
        async with self.cache_manager.invalidating(service_def_path):
            await run_in_pool(
                Pool.STORAGE,
                self.cloud_storage_manager.save_small_file,
                file_content=service_def_yaml.encode('utf-8'),
                bucket_name=self.application_bucket,
                key=service_def_path,
                content_type='application/yaml',
            )
            return await self.api_services_repository.create(
                id=id, service_def_path=service_def_path
            )

    async def fetch_service_def(self, api_services: ApiServices) -> str:
        service_def_path = f'api_services/{api_services.id}.yaml'

        async def load() -> str:
            yaml_bytes: bytes = await run_in_pool(
                Pool.STORAGE,
                self.cloud_storage_manager.read_file,
                bucket_name=self.application_bucket,
                file_path=service_def_path,
            )
            return yaml_bytes.decode('utf-8')

        return await self.cache_manager.read_through(
            service_def_path, load, ttl=_DEFINITION_CACHE_SECONDS
        )

    async def get_api_service(self, id: str) -> ApiServices | None:
        """Get an API service by id."""
        return await self.api_services_repository.find_one(id=id)

    async def get_all_api_services(self) -> List[ApiServices] | None:
        """Get all API services."""
        return await self.api_services_repository.find()

    async def update_api_service(self, id: str, service_def_yaml: str) -> bool:
        """Update an API service.

        The reload that follows reads the definition through the cache, so the
        change is wrapped in a strict invalidation: with Redis down this fails
        (503) before anything changes, and the old definition can never be
        reloaded after a successful update.
        """
        service_def_path = f'api_services/{id}.yaml'
        async with self.cache_manager.invalidating(service_def_path):
            await run_in_pool(
                Pool.STORAGE,
                self.cloud_storage_manager.save_small_file,
                file_content=service_def_yaml.encode('utf-8'),
                bucket_name=self.application_bucket,
                key=service_def_path,
                content_type='application/yaml',
            )
            await self.api_services_repository.find_one_and_update(
                filters={'id': id}, update_data={'service_def_path': service_def_path}
            )
        return True

    async def delete_api_service(self, id: str) -> bool:
        """Delete an API service.

        Storage first: if the storage pool is busy (a 503), nothing has been
        deleted yet and a retry works. Deleting the DB row first would leave an
        orphaned file and a lingering cache entry, and the retry would 404.

        Any other storage error (including the file already being gone, which
        GCS and Azure raise on) is logged and the delete carries on: an orphaned
        file is harmless, but a row whose file is gone could never be deleted.
        """
        service_def_path = f'api_services/{id}.yaml'
        async with self.cache_manager.invalidating(service_def_path):
            try:
                await run_in_pool(
                    Pool.STORAGE,
                    self.cloud_storage_manager.delete_file,
                    bucket_name=self.application_bucket,
                    file_path=service_def_path,
                )
            except BlockingPoolBusyError:
                raise
            except Exception as e:
                logger.warning(
                    f'Could not delete {service_def_path} from storage; '
                    f'deleting the API service anyway: {e}'
                )
            await self.api_services_repository.delete_all(id=id)
        return True

    async def deactivate_api_service(self, id: str) -> bool:
        """Deactivate an API service."""
        return await self.api_services_repository.find_one_and_update(
            filters={'id': id}, update_data={'is_active': False}
        )

    async def activate_api_service(self, id: str) -> bool:
        """Activate an API service."""
        return await self.api_services_repository.find_one_and_update(
            filters={'id': id}, update_data={'is_active': True}
        )
