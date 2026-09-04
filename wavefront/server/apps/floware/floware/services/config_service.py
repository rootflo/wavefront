from typing import Any

from fastapi import UploadFile, File, HTTPException
from flo_cloud.cloud_storage import CloudStorageManager
from floware.repositories.config_repository import AppConfigRepository
from floware.repositories.datasource_repository import AppDatasourceRepository
from floware.repositories.knowledge_base_repository import AppKnowledgeBaseRepository


class ConfigService:
    def __init__(
        self,
        app_config_repository: AppConfigRepository,
        datasource_repository: AppDatasourceRepository,
        knowledge_base_repository: AppKnowledgeBaseRepository,
        cloud_storage_manager: CloudStorageManager,
        config: dict[str, Any],
    ) -> None:
        self.app_config_repository = app_config_repository
        self.datasource_repository = datasource_repository
        self.knowledge_base_repository = knowledge_base_repository
        self.cloud_storage_manager = cloud_storage_manager
        self.config = config

    def _get_floware_credentials(self) -> dict[str, Any]:
        config_credentials = self.config.get('floware')
        if not isinstance(config_credentials, dict):
            raise HTTPException(
                status_code=500, detail='Floware configuration is missing'
            )
        if not config_credentials.get(
            'asset_storage_bucket'
        ) or not config_credentials.get('config_file_name'):
            raise HTTPException(
                status_code=500, detail='Incomplete Floware configuration'
            )
        return config_credentials

    async def store_app_config(
        self,
        file: UploadFile | None = None,
        app_config: dict[str, Any] | None = None,
    ):
        file = file or File(None)
        config_credentials = self._get_floware_credentials()
        if file and file.content_type not in ['image/png', 'image/jpeg', 'image/jpg']:
            raise HTTPException(status_code=400, detail='Invalid file type')
        file_size = getattr(file, 'size', None)
        if file_size is not None and file_size > 1024 * 1024 * 1:  # 1MB
            raise HTTPException(status_code=400, detail='File size is too large')

        file_content = await file.read() if file else None
        if file_content:
            self.cloud_storage_manager.save_small_file(
                file_content,
                config_credentials['asset_storage_bucket'],
                config_credentials['config_file_name'],
            )
        # if atleast one icon or file_content is there then allow the all_config to be saved
        config_data = await self.app_config_repository.get()
        if config_data and config_data.get('app_icon') or file_content:
            await self.app_config_repository.upsert(
                {
                    'app_icon': config_credentials['config_file_name'],
                    'app_config': app_config if app_config else {},
                }
            )
        else:
            raise HTTPException(status_code=400, detail='App icon is not set')
        return

    async def get_app_config(self):
        config_record = await self.app_config_repository.get()
        if not config_record:
            return None, None
        config_path = config_record.get('app_icon')
        config_credentials = self._get_floware_credentials()
        url = self.cloud_storage_manager.generate_presigned_url(
            config_credentials['asset_storage_bucket'],
            config_path,
            'get',
        )
        app_config = config_record.get('app_config', {})
        return url, app_config

    async def get_settings_config(self) -> dict[str, Any]:
        """Full settings/config payload: app icon URL, app_config, and resource lists."""
        url, app_config = await self.get_app_config()
        datasources = await self.datasource_repository.get_all()
        knowledge_bases = await self.knowledge_base_repository.get_all()
        return {
            'app_icon': url,
            'app_config': app_config,
            'datasources': datasources,
            'knowledgebases': knowledge_bases,
        }
