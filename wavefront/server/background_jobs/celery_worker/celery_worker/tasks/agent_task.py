"""Celery task: async agent inference."""

import asyncio
from typing import Dict
from uuid import UUID

from agents_module.utils.trace_utils import serialize_conversation_trace
from common_module.log.logger import logger

from celery_worker.celery_app import app
from celery_worker.event_loop import get_event_loop
from celery_worker.services import get_services
from celery_worker.settings import MAX_RETRIES, RETRY_DELAY
from celery_worker.tasks.helpers import (
    build_history,
    build_llm_config,
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
        llm_config = build_llm_config(payload.get('llm_config'))

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
        trace = (
            serialize_conversation_trace('agent', result)
            if isinstance(result, list)
            else []
        )

        output_key = f"{payload['output_prefix']}output.json"
        history_key = f"{payload['output_prefix']}history.json"
        bucket = payload['execution_bucket']

        save_json(
            services.cloud_storage,
            bucket,
            output_key,
            {
                'result': final_result,
                'execution_time_seconds': round(exec_time, 3),
            },
        )
        save_json(
            services.cloud_storage,
            bucket,
            history_key,
            build_history(payload, final_result, exec_time, trace),
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
        logger.info(f'Agent execution completed: {execution_id} in {exec_time:.2f}s')

    except Exception as exc:
        error_msg = str(exc)
        logger.error(f'Agent execution failed: {execution_id} — {error_msg}')

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
    name='celery_worker.tasks.agent_task.execute_agent_task',
    max_retries=MAX_RETRIES,
    default_retry_delay=RETRY_DELAY,
)
def execute_agent_task(self, payload: Dict) -> None:
    # Shared process-lifetime loop — see get_event_loop(). Pending client
    # finalizers stay scheduled on it and run during the next task instead of
    # being orphaned on a closed loop.
    get_event_loop().run_until_complete(_run(self, payload))
