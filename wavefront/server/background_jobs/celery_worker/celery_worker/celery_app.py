from celery import Celery
from celery.signals import (
    worker_process_init,
    worker_process_shutdown,
    worker_shutdown,
)

from celery_worker.env import CELERY_BROKER_URL, CELERY_RESULT_BACKEND


@worker_process_init.connect
def setup_azure_redis_auth(**kwargs):
    from db_repo_module.cache.azure_redis_auth import patch_redis_for_azure

    patch_redis_for_azure()


def teardown_event_loop(**kwargs):
    from celery_worker.worker_setup import close_event_loop

    close_event_loop()


# Only the prefork pool dispatches worker_process_shutdown (celery/concurrency/
# prefork.py) — under solo it never fires, and solo is where the loop lives in
# the main process. Hook the worker-level signal too, which fires for every
# pool. close_event_loop() is idempotent, so a double-fire is harmless.
worker_process_shutdown.connect(teardown_event_loop, weak=False)
worker_shutdown.connect(teardown_event_loop, weak=False)


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
    # An idle worker's result-backend socket gets closed by Azure Redis / the LB
    # after minutes of no traffic, and redis-py only notices on the next command.
    # health_check_interval makes it PING-before-use on any connection idle >30s
    # and transparently reconnect, so the first task after a long gap doesn't die
    # on a stale socket. always_retry covers get_task_meta/store_result, which
    # result_backend_transport_options['retry_policy'] does NOT reach (it only
    # feeds ensure(), and RedisBackend.get is unwrapped).
    redis_backend_health_check_interval=30,
    redis_socket_keepalive=True,
    redis_retry_on_timeout=True,
    result_backend_always_retry=True,
    result_backend_max_retries=5,
    broker_transport_options={
        'unacked_key': '{celery}.unacked',
        'unacked_index_key': '{celery}.unacked_index',
        'unacked_mutex_key': '{celery}.unacked_mutex',
    },
)
