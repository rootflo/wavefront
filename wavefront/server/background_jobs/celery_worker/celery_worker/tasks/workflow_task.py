import asyncio
from typing import Dict

from common_module.log.logger import logger

from celery_worker.celery_app import app
from celery_worker.env import MAX_RETRIES, RETRY_DELAY, STREAM_NAME
from celery_worker.tasks.agent_task import (
    _build_history,
    _now,
    _reconstruct_inputs,
    _save_json,
)
from celery_worker.worker_setup import get_services


async def _run(task, payload: Dict) -> None:
    services = get_services()
    execution_id = payload['execution_id']

    # Signal in_progress — floware consumer updates DB
    services.cache.xadd(
        STREAM_NAME,
        {
            'execution_id': execution_id,
            'status': 'in_progress',
            'started_at': _now(),
            'error': '',
        },
    )

    try:
        inputs = _reconstruct_inputs(payload, services.cloud_storage)

        result, exec_time = await services.workflow_inference.perform_inference_v2(
            workflow_data={
                'id': payload['entity_id'],
                'name': payload['workflow_name'],
                'namespace': payload['namespace'],
            },
            variables=payload.get('variables') or {},
            inputs=inputs if isinstance(inputs, list) else [inputs],
            output_json_enabled=payload.get('output_json_enabled', False),
            event_callback=None,
            events_filter=None,
            access_token=payload.get('access_token'),
            app_key=payload.get('app_key'),
        )

        output_key = f"{payload['output_prefix']}output.json"
        history_key = f"{payload['output_prefix']}history.json"
        bucket = payload['execution_bucket']

        _save_json(
            services.cloud_storage,
            bucket,
            output_key,
            {
                'result': result,
                'execution_time_seconds': round(exec_time, 3),
            },
        )
        _save_json(
            services.cloud_storage,
            bucket,
            history_key,
            _build_history(payload, result, exec_time),
        )

        # Signal completed — floware consumer updates DB
        services.cache.xadd(
            STREAM_NAME,
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
        logger.info(f'Workflow execution completed: {execution_id} in {exec_time:.2f}s')

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f'Workflow execution failed: {execution_id} — {error_msg}')

        # Signal failed — floware consumer updates DB
        services.cache.xadd(
            STREAM_NAME,
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
    name='celery_worker.tasks.workflow_task.execute_workflow_task',
    max_retries=MAX_RETRIES,
    default_retry_delay=RETRY_DELAY,
)
def execute_workflow_task(self, payload: Dict) -> None:
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run(self, payload))
    finally:
        pending = asyncio.all_tasks(loop)
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()
