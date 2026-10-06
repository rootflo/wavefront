from celery import Celery

from agents_module.runtime_config import get_celery_broker_url


def get_celery_client() -> Celery:
    app = Celery('async_executor', broker=get_celery_broker_url())
    app.conf.task_default_queue = '{celery}'
    return app
