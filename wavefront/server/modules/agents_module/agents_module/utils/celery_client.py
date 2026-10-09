from celery import Celery


def build_celery_client(broker_url: str) -> Celery:
    app = Celery('async_executor', broker=broker_url)
    app.conf.task_default_queue = '{celery}'
    return app
