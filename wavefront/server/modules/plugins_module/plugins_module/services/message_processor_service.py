"""
Service for managing and executing functions stored in cloud storage buckets.
YAML files are stored directly in buckets, and only the file URL is stored in the database.
"""

import contextlib

import yaml
from typing import Dict, Any, Optional, List
from uuid import uuid4
import flo_lib.http as http

from common_module.blocking_io import Pool, run_in_pool
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.message_processors import MessageProcessors
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from flo_cloud.cloud_storage import CloudStorageManager
from common_module.log.logger import logger

# Function Definition Schema v1.0 for reference
sample_yaml = """
function:
  code: |
    export default function(input) {
      return {
        success: true,
        message: input.message,
        source: input.source,
        timestamp: new Date().toISOString(),
      };
    }

input_schema:
  required:
    - message
    - source
  properties:
    message:
      type: string
      description: The message to process
    source:
      type: string
      description: The source of the message

environment:
  variables:
    - name: LOG_LEVEL
      value: "info"
    - name: API_URL
      value: "https://api.example.com"

"""


class HermesClient:
    def __init__(self, hermes_url: str):
        self.hermes_url = hermes_url

    async def execute_code(
        self, code: str, type: str, input: Dict[str, Any]
    ) -> Dict[str, Any]:
        async with http.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f'{self.hermes_url}/execute',
                json={
                    'code': code,
                    'type': type,
                    'input': input,
                },
            )
        resp_json = resp.json()
        if resp.status_code != 200:
            raise Exception(resp_json['details'])
        return resp_json


_DEFAULT_YAML_CACHE_SECONDS = 3600


class MessageProcessorService:
    """Service for managing function processors stored in cloud storage."""

    def __init__(
        self,
        cloud_storage_manager: CloudStorageManager,
        message_processor_repository: SQLAlchemyRepository[MessageProcessors],
        hermes_url: str,
        bucket_name: Optional[str] = None,
        cache_manager: Optional[CacheManager] = None,
        yaml_cache_seconds: Optional[int | str] = None,
    ):
        self.cloud_storage_manager = cloud_storage_manager
        self.message_processor_repository = message_processor_repository
        self.bucket_name = bucket_name
        self.prefix = 'message_processors/v1'
        self.hermes_client = HermesClient(hermes_url=hermes_url)
        # Every write goes through this service, so it keeps the cached YAML
        # current; the TTL bounds staleness if a cache write fails. 0 = off.
        self.yaml_cache_seconds = (
            _DEFAULT_YAML_CACHE_SECONDS
            if yaml_cache_seconds in (None, '')
            else int(yaml_cache_seconds)
        )
        if self.yaml_cache_seconds < 0:
            raise ValueError('yaml_cache_seconds must be 0 or more')
        self.cache_manager = cache_manager if self.yaml_cache_seconds > 0 else None

    async def create_message_processor(
        self, name: str, yaml_content: str, description: Optional[str] = None
    ) -> MessageProcessors:
        message_processor_id = uuid4()
        file_name = f'{message_processor_id}.yaml'
        file_path = f'{self.prefix}/{file_name}'
        await self.save_message_processor_yaml(
            yaml_content=yaml_content, file_path=file_path
        )
        return await self.message_processor_repository.create(
            id=message_processor_id,
            name=name,
            description=description,
            source=file_name,
        )

    async def save_message_processor_yaml(
        self, yaml_content: str, file_path: str
    ) -> None:
        yaml_dict = yaml.safe_load(yaml_content)
        # Validate required top-level fields
        if not yaml_dict:
            raise ValueError('YAML content is empty or invalid')

        required_fields = ['function', 'input_schema', 'type', 'description']
        missing_fields = [field for field in required_fields if field not in yaml_dict]
        if missing_fields:
            raise ValueError(f'YAML must contain required fields: {missing_fields}')

        # Validate input_schema structure
        if 'required' not in yaml_dict['input_schema']:
            raise ValueError("YAML input_schema must contain 'required' field")

        # Store YAML file in bucket
        yaml_bytes = yaml_content.encode('utf-8')
        async with self._invalidating(file_path):
            await run_in_pool(
                Pool.STORAGE,
                self.cloud_storage_manager.save_small_file,
                file_content=yaml_bytes,
                bucket_name=self.bucket_name,
                key=file_path,
                disable_cache=True,
            )
        logger.info(f'Stored YAML file at {self.bucket_name}/{file_path}')

    async def get_message_processor(self, **kwargs) -> Optional[MessageProcessors]:
        return await self.message_processor_repository.find_one(**kwargs)

    async def get_message_processor_yaml_content(
        self, processor: MessageProcessors
    ) -> str:
        filepath = f'{self.prefix}/{processor.source}'

        async def load() -> str:
            yaml_bytes = await run_in_pool(
                Pool.STORAGE,
                self.cloud_storage_manager.read_file,
                self.bucket_name,
                filepath,
            )
            return yaml_bytes.decode('utf-8')

        if self.cache_manager is None:
            return await load()
        return await self.cache_manager.read_through(
            self._yaml_cache_key(filepath), load, ttl=self.yaml_cache_seconds
        )

    async def list_message_processors(self) -> List[MessageProcessors]:
        processors = await self.message_processor_repository.find()
        return processors

    async def update_message_processor(
        self,
        processor: MessageProcessors,
        updates: Dict[str, Any],
        yaml_content: Optional[str] = None,
    ) -> Optional[MessageProcessors]:
        if yaml_content is not None:
            file_path = f'{self.prefix}/{processor.source}'
            await self.save_message_processor_yaml(
                yaml_content=yaml_content, file_path=file_path
            )

        for key, value in updates.items():
            if hasattr(processor, key):
                setattr(processor, key, value)

        return await self.message_processor_repository.find_one_and_update(
            filters={'id': processor.id}, refresh=True, **updates
        )

    async def delete_message_processor(self, processor_id: str) -> bool:
        processor = await self.get_message_processor(id=processor_id)
        if not processor:
            return False

        file_path = f'{self.prefix}/{processor.source}'
        async with self._invalidating(file_path):
            await run_in_pool(
                Pool.STORAGE,
                self.cloud_storage_manager.delete_file,
                self.bucket_name,
                file_path,
            )
        logger.info(f'Deleted YAML file at {self.bucket_name}/{file_path}')

        await self.message_processor_repository.delete_all(id=processor_id)
        return True

    async def execute_message_processor(
        self, code: str, type: str, input: Dict[str, Any]
    ) -> Dict[str, Any]:
        result = await self.hermes_client.execute_code(
            code=code, type=type, input=input
        )
        return result

    # YAML cache: generation-checked (CacheManager.read_through/invalidating),
    # so a read racing an update or delete can never put the old YAML back.
    # Writes are strict: with Redis down they fail (503) before storage changes.

    @staticmethod
    def _yaml_cache_key(file_path: str) -> str:
        return f'message_processor_yaml/{file_path}'

    def _invalidating(self, file_path: str):
        if self.cache_manager is None:
            return contextlib.nullcontext()
        return self.cache_manager.invalidating(self._yaml_cache_key(file_path))
