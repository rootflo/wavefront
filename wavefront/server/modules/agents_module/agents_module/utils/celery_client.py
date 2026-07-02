import os

from celery import Celery


def get_celery_client() -> Celery:
    broker_url = os.getenv('CELERY_BROKER_URL')
    if not broker_url:
        raise RuntimeError('Missing required env var: CELERY_BROKER_URL')
    app = Celery('async_executor', broker=broker_url)
    app.conf.task_default_queue = '{celery}'
    return app
