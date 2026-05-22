import asyncio
from typing import Any, Dict
from uuid import UUID

from common_module.log.logger import logger

from celery_worker.celery_app import app
from celery_worker.env import MAX_RETRIES, RETRY_DELAY
from celery_worker.worker_setup import get_services


@app.task(
    name='celery_worker.tasks.trigger_event_task.process_trigger_event_task',
    bind=True,
    max_retries=MAX_RETRIES,
    default_retry_delay=RETRY_DELAY,
)
def process_trigger_event_task(
    self, trigger_id: str, raw_payload: Dict[str, Any], push_message_id: str
) -> Dict[str, Any]:
    services = get_services()
    processor = services.trigger_event_processor

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            processor.process(trigger_id=UUID(trigger_id), raw_payload=raw_payload)
        )
    except Exception as exc:
        logger.exception(
            f'process_trigger_event_task failed for trigger {trigger_id} '
            f'(push_message_id={push_message_id}): {exc}'
        )
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise
    finally:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        try:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass
        loop.close()
