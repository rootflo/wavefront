"""Celery application instance for the async executor worker."""

from celery import Celery

from celery_worker.settings import CELERY_BROKER_URL, CELERY_RESULT_BACKEND

# Connect worker_process_init / shutdown handlers (telemetry + event loop).
import celery_worker.signals  # noqa: F401

app = Celery('async_executor')
app.conf.update(
    broker_url=CELERY_BROKER_URL,
    result_backend=CELERY_RESULT_BACKEND,
    include=[
        'celery_worker.tasks.agent_task',
        'celery_worker.tasks.workflow_task',
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
