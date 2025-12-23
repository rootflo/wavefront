"""
Service for managing and executing functions stored in cloud storage buckets.
YAML files are stored directly in buckets, and only the file URL is stored in the database.
"""

import yaml
from typing import Dict, Any, Optional, List
from uuid import uuid4
import requests
import asyncio

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
        def _do_request():
            resp = requests.post(
                f'{self.hermes_url}/execute',
                json={
                    'code': code,
                    'type': type,
                    'input': input,
                },
                timeout=10,
            )
            resp_json = resp.json()
            if resp.status_code != 200:
                raise Exception(resp_json['details'])
            return resp_json

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _do_request)


class MessageProcessorService:
    """Service for managing function processors stored in cloud storage."""

    def __init__(
        self,
        cloud_manager: CloudStorageManager,
        message_processor_repository: SQLAlchemyRepository[MessageProcessors],
        bucket_name: str,
        hermes_url: str,
    ):
        self.cloud_manager = cloud_manager
        self.message_processor_repository = message_processor_repository
        self.bucket_name = bucket_name
        self.prefix = 'message_processors/v1'
        self.hermes_client = HermesClient(hermes_url=hermes_url)

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
        self.cloud_manager.save_small_file(
            file_content=yaml_bytes, bucket_name=self.bucket_name, key=file_path
        )
        logger.info(f'Stored YAML file at {self.bucket_name}/{file_path}')

    async def get_message_processor(self, **kwargs) -> Optional[MessageProcessors]:
        return await self.message_processor_repository.find_one(**kwargs)

    async def get_message_processor_yaml_content(
        self, processor: MessageProcessors
    ) -> str:
        filepath = f'{self.prefix}/{processor.source}'
        yaml_bytes = self.cloud_manager.read_file(self.bucket_name, filepath)
        return yaml_bytes.decode('utf-8')

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
        self.cloud_manager.delete_file(self.bucket_name, file_path)
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
