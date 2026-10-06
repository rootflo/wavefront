"""Celery task: async workflow inference."""

import asyncio
from typing import Dict

from common_module.log.logger import logger

from celery_worker.celery_app import app
from celery_worker.event_loop import get_event_loop
from celery_worker.services import get_services
from celery_worker.settings import MAX_RETRIES, RETRY_DELAY
from celery_worker.tasks.helpers import (
    build_history,
    now_iso,
    publish_result,
    reconstruct_inputs,
    save_json,
)


async def _run(task, payload: Dict) -> None:
    services = get_services()
    execution_id = payload['execution_id']

    publish_result(
        services.cache,
        execution_id,
        {
            'execution_id': execution_id,
            'status': 'in_progress',
            'started_at': now_iso(),
            'error': '',
        },
    )

    try:
        inputs = await asyncio.to_thread(
            reconstruct_inputs, payload, services.cloud_storage
        )

        (
            result,
            exec_time,
            trace,
        ) = await services.workflow_inference.perform_inference_v2(
            workflow_data={
                'id': payload['entity_id'],
                'name': payload['workflow_name'],
                'namespace': payload['namespace'],
                'version': payload.get('version'),
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

        save_json(
            services.cloud_storage,
            bucket,
            output_key,
            {
                'result': result,
                'execution_time_seconds': round(exec_time, 3),
            },
        )
        save_json(
            services.cloud_storage,
            bucket,
            history_key,
            build_history(payload, result, exec_time, trace),
        )

        publish_result(
            services.cache,
            execution_id,
            {
                'execution_id': execution_id,
                'status': 'completed',
                'output_file': output_key,
                'history_file': history_key,
                'input_bucket': bucket,
                'completed_at': now_iso(),
                'error': '',
            },
        )
        logger.info(f'Workflow execution completed: {execution_id} in {exec_time:.2f}s')

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f'Workflow execution failed: {execution_id} — {error_msg}')

        publish_result(
            services.cache,
            execution_id,
            {
                'execution_id': execution_id,
                'status': 'failed',
                'error': error_msg,
                'completed_at': now_iso(),
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
    # Shared process-lifetime loop — see get_event_loop().
    get_event_loop().run_until_complete(_run(self, payload))
