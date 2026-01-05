from typing import Any

from db_repo_module.models.config import Config
from fastapi import UploadFile, File, HTTPException
from flo_cloud.cloud_storage import CloudStorageManager
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository


class ConfigService:
    def __init__(
        self,
        config_repository: SQLAlchemyRepository[Config],
        cloud_manager: CloudStorageManager,
        config: dict[str, Any],
    ) -> None:
        self.config_repository = config_repository
        self.cloud_manager = cloud_manager
        self.config = config

    def _get_gcp_credentials(self) -> dict[str, Any]:
        config_credentials = self.config.get('gcp')
        if not isinstance(config_credentials, dict):
            raise HTTPException(status_code=500, detail='GCP configuration is missing')
        if not config_credentials.get(
            'gcp_asset_storage_bucket'
        ) or not config_credentials.get('config_file_name'):
            raise HTTPException(status_code=500, detail='Incomplete GCP configuration')
        return config_credentials

    async def store_app_config(
        self,
        file: UploadFile | None = None,
        app_config: dict[str, Any] | None = None,
    ):
        file = file or File(None)
        config_credentials = self._get_gcp_credentials()
        if file and file.content_type not in ['image/png', 'image/jpeg', 'image/jpg']:
            raise HTTPException(status_code=400, detail='Invalid file type')
        file_size = getattr(file, 'size', None)
        if file_size is not None and file_size > 1024 * 1024 * 1:  # 1MB
            raise HTTPException(status_code=400, detail='File size is too large')

        file_content = await file.read() if file else None
        if file_content:
            self.cloud_manager.save_small_file(
                file_content,
                config_credentials['gcp_asset_storage_bucket'],
                config_credentials['config_file_name'],
            )
        # if atleast one icon or file_content is there then allow the all_config to be saved
        config_data = await self.config_repository.find(key='app_config')
        if config_data and config_data[0].value.get('app_icon') or file_content:
            # saving the config to the database
            await self.config_repository.upsert(
                filters={'key': 'app_config'},
                value={
                    'app_icon': config_credentials['config_file_name'],
                    'app_config': app_config if app_config else {},
                },
            )
        else:
            raise HTTPException(status_code=400, detail='App icon is not set')
        return

    async def get_app_config(self):
        config_record = await self.config_repository.find(key='app_config')
        # checking if the config_record is empty
        if not config_record:
            return None, None
        config_path = config_record[0].value.get('app_icon')
        config_credentials = self._get_gcp_credentials()
        # Generate new presigned URL
        url = self.cloud_manager.generate_presigned_url(
            config_credentials['gcp_asset_storage_bucket'],
            config_path,
            'get',
        )
        # getting the app_config from the database
        app_config = config_record[0].value.get('app_config', {})

        return url, app_config
