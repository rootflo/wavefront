import re
from typing import Any

from celery import Celery

DEFAULT_QUEUE_NAME = 'celery'
_QUEUE_NAME_RE = re.compile(r'[A-Za-z0-9_.:-]+')


def _queue_name(name: Any) -> str:
    """The bare queue name; unset means the default, invalid raises.

    Never falls back on a bad value: that would route this app's tasks into
    another app's queue.
    """
    if name is None or str(name).strip() == '':
        return DEFAULT_QUEUE_NAME
    name = str(name).strip()
    if not _QUEUE_NAME_RE.fullmatch(name):
        raise ValueError(
            f'Celery queue_name {name!r} must match {_QUEUE_NAME_RE.pattern}'
        )
    return name


def celery_queue_key(name: Any) -> str:
    """Redis key of the queue. The braces are a Redis Cluster hash tag."""
    return '{' + _queue_name(name) + '}'


def celery_unacked_keys(name: Any) -> dict[str, str]:
    """kombu's unacked keys for the queue, in the queue's hash slot."""
    key = celery_queue_key(name)
    return {
        'unacked_key': f'{key}.unacked',
        'unacked_index_key': f'{key}.unacked_index',
        'unacked_mutex_key': f'{key}.unacked_mutex',
    }


def build_celery_client(broker_url: str, queue_name: Any = None) -> Celery:
    # queue_name must match the worker's; it separates apps sharing one Redis.
    app = Celery('async_executor', broker=broker_url)
    app.conf.task_default_queue = celery_queue_key(queue_name)
    return app
