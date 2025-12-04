from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.api_services import ApiServices
from flo_cloud.cloud_storage import CloudStorageManager
from typing import List
from api_services_module.env import SERVICE_DEFINITION_BUCKET


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

    async def create_api_service(
        self, id: str, service_def_yaml: str
    ) -> ApiServices | None:
        """Create a new API service."""
        service_def_path = f'api_services/{id}.yaml'
        self.cloud_storage_manager.save_small_file(
            file_content=service_def_yaml.encode('utf-8'),
            bucket_name=self._service_storage_bucket(),
            key=service_def_path,
            content_type='application/yaml',
        )
        self.cache_manager.add(service_def_path, service_def_yaml)
        return await self.api_services_repository.create(
            id=id, service_def_path=service_def_path
        )

    def fetch_service_def(self, api_services: ApiServices) -> str:
        service_def_path = f'api_services/{api_services.id}.yaml'
        cache_entry = self.cache_manager.get_str(service_def_path)
        if cache_entry:
            return cache_entry
        yaml_bytes: bytes = self.cloud_storage_manager.read_file(
            bucket_name=self._service_storage_bucket(), file_path=service_def_path
        )
        yaml_content = yaml_bytes.decode('utf-8')
        return yaml_content

    async def get_api_service(self, id: str) -> ApiServices | None:
        """Get an API service by id."""
        return await self.api_services_repository.find_one(id=id)

    async def get_all_api_services(self) -> List[ApiServices] | None:
        """Get all API services."""
        return await self.api_services_repository.find()

    async def update_api_service(self, id: str, service_def_yaml: str) -> bool:
        """Update an API service."""
        service_def_path = f'api_services/{id}.yaml'
        self.cloud_storage_manager.save_small_file(
            file_content=service_def_yaml.encode('utf-8'),
            bucket_name=self._service_storage_bucket(),
            key=service_def_path,
            content_type='application/yaml',
        )
        await self.api_services_repository.find_one_and_update(
            filters={'id': id}, update_data={'service_def_path': service_def_path}
        )
        self.cache_manager.add(service_def_path, service_def_yaml)
        return True

    async def delete_api_service(self, id: str) -> bool:
        """Delete an API service."""
        service_def_path = f'api_services/{id}.yaml'
        await self.api_services_repository.delete_all(filters={'id': id})
        self.cloud_storage_manager.delete_file(
            bucket_name=self._service_storage_bucket(), file_path=service_def_path
        )
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

    def _service_storage_bucket(self) -> str:
        if not SERVICE_DEFINITION_BUCKET:
            raise ValueError(
                'SERVICE_DEFINITION_BUCKET is not set in the environment variables'
            )
        return SERVICE_DEFINITION_BUCKET
