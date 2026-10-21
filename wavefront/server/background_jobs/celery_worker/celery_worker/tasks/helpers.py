"""Shared helpers for agent and workflow Celery tasks."""

import base64
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents_module.utils.input_processing_utils import process_inference_inputs
from common_module.log.logger import logger
from db_repo_module.models.llm_inference_config import LlmInferenceConfig

from celery_worker.settings import STREAM_NAME


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_llm_config(llm_config_dict: Optional[Dict]) -> Optional[LlmInferenceConfig]:
    if not llm_config_dict:
        return None
    return LlmInferenceConfig(**llm_config_dict)


def reconstruct_inputs(payload: Dict, cloud_storage) -> Any:
    """
    Rebuild inputs from the clean JSON in the task payload.
    Stored binary entries are fetched from cloud storage and re-encoded to base64
    so that process_inference_inputs() can handle them normally.

    Blocking: each stored file is read from cloud storage synchronously and
    base64-encoded whole, so the tasks call it through `asyncio.to_thread` to
    keep that off the event loop. (Document parsing no longer happens here --
    flo_ai does it, off the loop, when it formats the message.)
    """
    raw_inputs = payload['inputs']

    if isinstance(raw_inputs, str):
        return process_inference_inputs(raw_inputs)

    rebuilt: List[Dict] = []
    for entry in raw_inputs:
        if not isinstance(entry, dict) or not entry.get('stored'):
            rebuilt.append(entry)
            continue

        file_bytes = cloud_storage.read_file(entry['bucket'], entry['key'])
        b64 = base64.b64encode(file_bytes).decode('utf-8')
        input_type = entry.get('input_type', 'document')
        mime_type = entry.get('mime_type')
        file_name = entry.get('file_name')

        content: Dict = (
            {'document_base64': b64}
            if input_type == 'document'
            else {'image_base64': b64}
        )
        if mime_type:
            content['mime_type'] = mime_type
        if file_name:
            content['file_name'] = file_name

        rebuilt.append({'role': 'user', 'content': content})

    return process_inference_inputs(rebuilt)


def publish_result(cache, execution_id: str, fields: Dict) -> str:
    """Publish a status transition to the results stream, observably.

    Completion events have gone missing in production with no trace on either
    side, so log the attempt and the outcome. The returned stream message id is
    the important part: it proves the XADD reached Redis and gives an exact key
    to look up with XRANGE when a row is stuck.
    """
    status = fields.get('status')
    # Log the RESOLVED key. CacheManager prepends its namespace inside xadd, so
    # a worker and a consumer configured with different APP_NAMEs write and read
    # different Redis keys while logging the same stream name.
    resolved_key = f'{cache.namespace}/{STREAM_NAME}'
    logger.info(
        f'Publishing result event: execution_id={execution_id}, '
        f'status={status}, key={resolved_key}'
    )
    try:
        message_id = cache.xadd(STREAM_NAME, fields)
    except Exception:
        # Per-attempt errors are logged inside CacheManager.xadd; this fires
        # once, after tenacity has exhausted its retries.
        logger.exception(
            f'Publish FAILED: execution_id={execution_id}, status={status}, '
            f'key={resolved_key}'
        )
        raise

    logger.info(
        f'Published result event: execution_id={execution_id}, '
        f'status={status}, key={resolved_key}, message_id={message_id}'
    )
    return message_id


def save_json(cloud_storage, bucket: str, key: str, data: Any) -> None:
    cloud_storage.save_small_file(
        file_content=json.dumps(data, default=str).encode('utf-8'),
        bucket_name=bucket,
        key=key,
        content_type='application/json',
    )


def build_history(
    payload: Dict,
    result: Any,
    exec_time: float,
    trace: Optional[List[Dict[str, Any]]] = None,
) -> Dict:
    return {
        'execution_id': payload['execution_id'],
        'entity_type': payload['entity_type'],
        'entity_id': payload['entity_id'],
        'inputs': payload['inputs'],  # clean inputs with storage key refs
        'variables': payload.get('variables') or {},
        'output': result,
        'execution_time_seconds': round(exec_time, 3),
        'trace': trace or [],  # full per-node/turn memory, in execution order
    }
