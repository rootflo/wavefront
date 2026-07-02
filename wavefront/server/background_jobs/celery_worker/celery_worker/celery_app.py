from celery import Celery
from celery.signals import worker_process_init

from celery_worker.env import CELERY_BROKER_URL, CELERY_RESULT_BACKEND


@worker_process_init.connect
def setup_azure_redis_auth(**kwargs):
    from db_repo_module.cache.azure_redis_auth import patch_redis_for_azure

    patch_redis_for_azure()


app = Celery('async_executor')
app.conf.update(
    broker_url=CELERY_BROKER_URL,
    result_backend=CELERY_RESULT_BACKEND,
    include=[
        'celery_worker.tasks.agent_task',
        'celery_worker.tasks.workflow_task',
        'celery_worker.tasks.trigger_event_task',
    ],
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_acks_late=True,  # Only ack after successful processing
    task_reject_on_worker_lost=True,  # Re-queue on worker crash
    worker_prefetch_multiplier=1,  # Fair task distribution
    task_track_started=True,
    task_default_queue='{celery}',
    worker_enable_remote_control=False,
    broker_transport_options={
        'unacked_key': '{celery}.unacked',
        'unacked_index_key': '{celery}.unacked_index',
        'unacked_mutex_key': '{celery}.unacked_mutex',
    },
)
