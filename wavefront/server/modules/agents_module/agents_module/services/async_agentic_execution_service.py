import asyncio
import base64
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from common_module.log.logger import logger
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.async_agentic_execution import AsyncAgenticExecution
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from flo_cloud.cloud_storage import CloudStorageManager

from agents_module.models.async_agentic_execution_schemas import (
    AsyncInferenceResponse,
    AgenticExecutionStatusResponse,
)
from agents_module.utils.celery_client import get_celery_client

_MIME_TO_EXT = {
    'application/pdf': '.pdf',
    'image/png': '.png',
    'image/jpeg': '.jpg',
    'image/jpg': '.jpg',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'image/svg+xml': '.svg',
    'text/plain': '.txt',
    'text/csv': '.csv',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
}

_AGENT_TASK_NAME = 'celery_worker.tasks.agent_task.execute_agent_task'
_WORKFLOW_TASK_NAME = 'celery_worker.tasks.workflow_task.execute_workflow_task'

_STATUS_CACHE_TTL_TERMINAL = 3600  # 1 hour for completed/failed
_STATUS_CACHE_TTL_ACTIVE = 10  # 10 seconds for pending/in_progress


def _cache_key(execution_id: UUID) -> str:
    return f'async_agentic_exec:status:{execution_id}'


def _safe_filename(idx: int, file_name: Optional[str], mime_type: Optional[str]) -> str:
    if file_name:
        return f'{idx}_{file_name}'
    ext = _MIME_TO_EXT.get(mime_type or '', '.bin')
    return f'{idx}_file{ext}'


class AsyncAgenticExecutionService:
    def __init__(
        self,
        async_agentic_execution_repository: SQLAlchemyRepository[AsyncAgenticExecution],
        cloud_storage_manager: CloudStorageManager,
        cache_manager: CacheManager,
        executions_bucket: str,
    ):
        self.repo = async_agentic_execution_repository
        self.cloud_storage = cloud_storage_manager
        self.cache = cache_manager
        self.bucket = executions_bucket

    def pre_save_binary_inputs(
        self,
        inputs: Any,
        prefix: str,
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Saves document/image base64 payloads to cloud storage.
        Returns (clean_inputs, stored_files) where:
          - clean_inputs: JSON-serializable list — text messages unchanged,
            binary entries replaced with {stored:true, bucket, key, ...}
          - stored_files: file-only subset for the input_files DB column
        """
        if isinstance(inputs, str):
            return [{'role': 'user', 'content': inputs}], []

        clean_inputs: List[Dict] = []
        stored_files: List[Dict] = []

        for idx, item in enumerate(inputs):
            if not isinstance(item, dict):
                clean_inputs.append({'role': 'user', 'content': str(item)})
                continue

            role = item.get('role', 'user')
            content = item.get('content', '')

            if role == 'assistant':
                clean_inputs.append({'role': 'assistant', 'content': content})
                continue

            if isinstance(content, str):
                clean_inputs.append({'role': 'user', 'content': content})
                continue

            # Determine if binary input
            if isinstance(content, dict):
                doc_b64 = content.get('document_base64')
                img_b64 = content.get('image_base64')
                mime_type = content.get('mime_type')
                file_name = content.get('file_name')

                if doc_b64 is not None:
                    input_type = 'document'
                    raw_b64 = doc_b64
                elif img_b64 is not None:
                    input_type = 'image'
                    raw_b64 = img_b64
                    # Strip data URL prefix if present
                    if isinstance(raw_b64, str) and raw_b64.startswith('data:'):
                        parts = raw_b64.split(',', 1)
                        if len(parts) == 2:
                            header = parts[0]  # e.g. "data:image/png;base64"
                            raw_b64 = parts[1]
                            if not mime_type and ';' in header:
                                mime_type = header.split(':')[1].split(';')[0]
                else:
                    # Unknown content structure — pass through as-is
                    clean_inputs.append(item)
                    continue

                safe_name = _safe_filename(idx, file_name, mime_type)
                key = f'{prefix}inputs/{safe_name}'

                file_bytes = base64.b64decode(raw_b64)
                self.cloud_storage.save_small_file(
                    file_content=file_bytes,
                    bucket_name=self.bucket,
                    key=key,
                )

                ref = {
                    'role': 'user',
                    'stored': True,
                    'bucket': self.bucket,
                    'key': key,
                    'file_name': file_name or safe_name,
                    'mime_type': mime_type,
                    'input_type': input_type,
                }
                if content.get('file_name'):
                    ref['original_file_name'] = content['file_name']

                clean_inputs.append(ref)
                stored_files.append(
                    {
                        'key': key,
                        'file_name': file_name or safe_name,
                        'mime_type': mime_type,
                        'input_type': input_type,
                    }
                )
            else:
                clean_inputs.append(item)

        return clean_inputs, stored_files

    async def create_and_enqueue_agent(
        self,
        agent_id: UUID,
        inputs: Any,
        variables: Optional[Dict[str, Any]],
        output_json_enabled: bool,
        access_token: Optional[str],
        app_key: Optional[str],
        llm_config: Optional[Dict] = None,
    ) -> AsyncInferenceResponse:
        execution_id = uuid.uuid4()
        prefix = f'executions/agents/{agent_id}/{execution_id}/'

        clean_inputs, stored_files = await asyncio.to_thread(
            self.pre_save_binary_inputs, inputs, prefix
        )

        await self.repo.create(
            id=execution_id,
            entity_type='agent',
            entity_id=agent_id,
            status='pending',
            input_bucket=self.bucket,
            inputs=json.dumps(clean_inputs),
            input_files=json.dumps(stored_files) if stored_files else None,
        )

        payload = {
            'execution_id': str(execution_id),
            'entity_id': str(agent_id),
            'entity_type': 'agent',
            'variables': variables or {},
            'inputs': clean_inputs,
            'llm_config': llm_config,
            'output_json_enabled': output_json_enabled,
            'access_token': access_token,
            'app_key': app_key,
            'execution_bucket': self.bucket,
            'output_prefix': prefix,
        }

        result = get_celery_client().send_task(
            _AGENT_TASK_NAME,
            kwargs={'payload': payload},
        )

        await self.repo.find_one_and_update(
            {'id': execution_id}, celery_task_id=result.id
        )

        logger.info(f'Enqueued agent execution {execution_id}, celery task {result.id}')
        return AsyncInferenceResponse(
            execution_id=execution_id,
            status='pending',
            entity_type='agent',
            entity_id=agent_id,
            status_url=f'/v1/agentic-executions/{execution_id}',
        )

    async def create_and_enqueue_workflow(
        self,
        workflow_id: UUID,
        workflow_name: str,
        namespace: str,
        inputs: Any,
        variables: Optional[Dict[str, Any]],
        output_json_enabled: bool,
        access_token: Optional[str],
        app_key: Optional[str],
    ) -> AsyncInferenceResponse:
        execution_id = uuid.uuid4()
        prefix = f'executions/workflows/{workflow_id}/{execution_id}/'

        clean_inputs, stored_files = await asyncio.to_thread(
            self.pre_save_binary_inputs, inputs, prefix
        )

        await self.repo.create(
            id=execution_id,
            entity_type='workflow',
            entity_id=workflow_id,
            status='pending',
            input_bucket=self.bucket,
            inputs=json.dumps(clean_inputs),
            input_files=json.dumps(stored_files) if stored_files else None,
        )

        payload = {
            'execution_id': str(execution_id),
            'entity_id': str(workflow_id),
            'entity_type': 'workflow',
            'workflow_name': workflow_name,
            'namespace': namespace,
            'variables': variables or {},
            'inputs': clean_inputs,
            'llm_config': None,
            'output_json_enabled': output_json_enabled,
            'access_token': access_token,
            'app_key': app_key,
            'execution_bucket': self.bucket,
            'output_prefix': prefix,
        }

        result = get_celery_client().send_task(
            _WORKFLOW_TASK_NAME,
            kwargs={'payload': payload},
        )

        await self.repo.find_one_and_update(
            {'id': execution_id}, celery_task_id=result.id
        )

        logger.info(
            f'Enqueued workflow execution {execution_id}, celery task {result.id}'
        )
        return AsyncInferenceResponse(
            execution_id=execution_id,
            status='pending',
            entity_type='workflow',
            entity_id=workflow_id,
            status_url=f'/v1/agentic-executions/{execution_id}',
        )

    def _build_status_response(
        self, record_dict: Dict
    ) -> AgenticExecutionStatusResponse:
        output_url = None
        history_url = None

        if record_dict.get('output_file') and record_dict.get('input_bucket'):
            try:
                output_url = self.cloud_storage.generate_presigned_url(
                    bucket_name=record_dict['input_bucket'],
                    key=record_dict['output_file'],
                    type='get',
                    expiresIn=900,
                )
            except Exception as e:
                logger.warning(f'Failed to generate output presigned URL: {e}')

        if record_dict.get('history_file') and record_dict.get('input_bucket'):
            try:
                history_url = self.cloud_storage.generate_presigned_url(
                    bucket_name=record_dict['input_bucket'],
                    key=record_dict['history_file'],
                    type='get',
                    expiresIn=900,
                )
            except Exception as e:
                logger.warning(f'Failed to generate history presigned URL: {e}')

        input_files = None
        if record_dict.get('input_files'):
            try:
                input_files = json.loads(record_dict['input_files'])
            except Exception:
                pass

        return AgenticExecutionStatusResponse(
            id=uuid.UUID(record_dict['id']),
            entity_type=record_dict['entity_type'],
            entity_id=uuid.UUID(record_dict['entity_id']),
            celery_task_id=record_dict.get('celery_task_id'),
            status=record_dict['status'],
            error=record_dict.get('error'),
            input_files=input_files,
            output_url=output_url,
            history_url=history_url,
            started_at=datetime.fromisoformat(record_dict['started_at'])
            if record_dict.get('started_at')
            else None,
            completed_at=datetime.fromisoformat(record_dict['completed_at'])
            if record_dict.get('completed_at')
            else None,
            created_at=datetime.fromisoformat(record_dict['created_at']),
        )

    async def get_execution_status(
        self, execution_id: UUID
    ) -> AgenticExecutionStatusResponse:
        cache_key = _cache_key(execution_id)
        cached = await asyncio.to_thread(self.cache.get_str, cache_key)

        if cached:
            logger.debug(f'Cache hit for execution status {execution_id}')
            return self._build_status_response(json.loads(cached))

        record = await self.repo.find_one(id=execution_id)
        if not record:
            raise ValueError(f'Execution not found: {execution_id}')

        record_dict = record.to_dict()
        status = record_dict['status']
        ttl = (
            _STATUS_CACHE_TTL_TERMINAL
            if status in ('completed', 'failed')
            else _STATUS_CACHE_TTL_ACTIVE
        )
        await asyncio.to_thread(self.cache.add, cache_key, json.dumps(record_dict), ttl)

        return self._build_status_response(record_dict)

    async def list_executions(
        self,
        entity_id: Optional[UUID] = None,
        entity_type: Optional[str] = None,
        status: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> List[AgenticExecutionStatusResponse]:
        filters: Dict[str, Any] = {}
        if entity_id:
            filters['entity_id'] = entity_id
        if entity_type:
            filters['entity_type'] = entity_type
        if status:
            filters['status'] = status

        records = await self.repo.find(**filters, limit=limit)
        records = records[offset:]

        return [self._build_status_response(r.to_dict()) for r in records]
