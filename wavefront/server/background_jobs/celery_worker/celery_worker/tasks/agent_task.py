import base64
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from common_module.log.logger import logger
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from agents_module.utils.input_processing_utils import process_inference_inputs

from celery_worker.celery_app import app
from celery_worker.env import MAX_RETRIES, RETRY_DELAY, STREAM_NAME
from celery_worker.worker_setup import get_event_loop, get_services


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_llm_config(llm_config_dict: Optional[Dict]) -> Optional[LlmInferenceConfig]:
    if not llm_config_dict:
        return None
    return LlmInferenceConfig(**llm_config_dict)


def _reconstruct_inputs(payload: Dict, cloud_storage) -> Any:
    """
    Rebuild inputs from the clean JSON in the task payload.
    Stored binary entries are fetched from cloud storage and re-encoded to base64
    so that process_inference_inputs() can handle them normally.
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


def _publish(cache, execution_id: str, fields: Dict) -> str:
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


def _save_json(cloud_storage, bucket: str, key: str, data: Any) -> None:
    cloud_storage.save_small_file(
        file_content=json.dumps(data, default=str).encode('utf-8'),
        bucket_name=bucket,
        key=key,
        content_type='application/json',
    )


def _build_history(payload: Dict, result: Any, exec_time: float) -> Dict:
    return {
        'execution_id': payload['execution_id'],
        'entity_type': payload['entity_type'],
        'entity_id': payload['entity_id'],
        'inputs': payload['inputs'],  # clean inputs with storage key refs
        'variables': payload.get('variables') or {},
        'output': result,
        'execution_time_seconds': round(exec_time, 3),
    }


async def _run(task, payload: Dict) -> None:
    services = get_services()
    execution_id = payload['execution_id']

    # Signal in_progress — floware consumer updates DB
    _publish(
        services.cache,
        execution_id,
        {
            'execution_id': execution_id,
            'status': 'in_progress',
            'started_at': _now(),
            'error': '',
        },
    )

    try:
        inputs = _reconstruct_inputs(payload, services.cloud_storage)
        llm_config = _build_llm_config(payload.get('llm_config'))

        (
            result,
            exec_time,
            _namespace,
        ) = await services.agent_inference.perform_inference_v2(
            agent_id=UUID(payload['entity_id']),
            variables=payload.get('variables') or {},
            inputs=inputs if isinstance(inputs, list) else [inputs],
            llm_config=llm_config,
            output_json_enabled=payload.get('output_json_enabled', True),
            access_token=payload.get('access_token'),
            app_key=payload.get('app_key'),
            version=payload.get('version'),
        )

        final_result = result[-1].content if isinstance(result, list) else result

        output_key = f"{payload['output_prefix']}output.json"
        history_key = f"{payload['output_prefix']}history.json"
        bucket = payload['execution_bucket']

        _save_json(
            services.cloud_storage,
            bucket,
            output_key,
            {
                'result': final_result,
                'execution_time_seconds': round(exec_time, 3),
            },
        )
        _save_json(
            services.cloud_storage,
            bucket,
            history_key,
            _build_history(payload, final_result, exec_time),
        )

        # Signal completed — floware consumer updates DB
        _publish(
            services.cache,
            execution_id,
            {
                'execution_id': execution_id,
                'status': 'completed',
                'output_file': output_key,
                'history_file': history_key,
                'input_bucket': bucket,
                'completed_at': _now(),
                'error': '',
            },
        )
        logger.info(f'Agent execution completed: {execution_id} in {exec_time:.2f}s')

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f'Agent execution failed: {execution_id} — {error_msg}')

        # Signal failed — floware consumer updates DB
        _publish(
            services.cache,
            execution_id,
            {
                'execution_id': execution_id,
                'status': 'failed',
                'error': error_msg,
                'completed_at': _now(),
            },
        )
        raise  # triggers Celery retry if MAX_RETRIES > 0


@app.task(
    bind=True,
    name='celery_worker.tasks.agent_task.execute_agent_task',
    max_retries=MAX_RETRIES,
    default_retry_delay=RETRY_DELAY,
)
def execute_agent_task(self, payload: Dict) -> None:
    # Shared process-lifetime loop — see get_event_loop(). Pending client
    # finalizers stay scheduled on it and run during the next task instead of
    # being orphaned on a closed loop.
    get_event_loop().run_until_complete(_run(self, payload))
