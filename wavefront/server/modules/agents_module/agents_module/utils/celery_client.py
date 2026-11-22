import re
from typing import Any

from celery import Celery

from agents_module.utils.celery_settings import CeleryProducerSettings

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


def build_celery_client(
    broker_url: str,
    queue_name: Any = None,
    settings: CeleryProducerSettings | None = None,
) -> Celery:
    # queue_name must match the worker's; it separates apps sharing one Redis.
    # set_as_current=False: this app is also built inside the worker, and the
    # default would replace the worker's own app.
    app = Celery('async_executor', broker=broker_url, set_as_current=False)
    app.conf.task_default_queue = celery_queue_key(queue_name)
    timeout = (settings or CeleryProducerSettings()).broker_socket_timeout_seconds
    app.conf.broker_transport_options = {
        'socket_timeout': timeout,
        'socket_connect_timeout': timeout,
    }
    return app
