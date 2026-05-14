from dotenv import load_dotenv


import os

from celery import Celery

load_dotenv()  # load .env before reading env vars

app = Celery('async_executor')
app.conf.update(
    broker_url=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    result_backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1'),
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
)
