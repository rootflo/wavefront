"""Per-app Celery queue. No broker is contacted."""

import pytest

from agents_module.agents_container import AgentsContainer
from agents_module.utils.celery_client import (
    build_celery_client,
    celery_queue_key,
    celery_unacked_keys,
)

BROKER = 'redis://localhost:6379/0'


@pytest.mark.parametrize('raw', [None, '', '   '])
def test_unset_queue_name_is_the_default(raw):
    assert celery_queue_key(raw) == '{celery}'
    assert build_celery_client(BROKER, raw).conf.task_default_queue == '{celery}'


def test_publishes_to_the_configured_queue():
    assert build_celery_client(BROKER, 'app2').conf.task_default_queue == '{app2}'
    assert celery_queue_key(' app2 ') == '{app2}'


@pytest.mark.parametrize('raw', ['{app2}', 'a}b', 'app 2', 'app/2'])
def test_invalid_queue_name_raises(raw):
    """Falling back would put this app's tasks in another app's queue."""
    with pytest.raises(ValueError):
        celery_queue_key(raw)


def test_unacked_keys_share_the_queue_hash_tag():
    assert celery_unacked_keys('app2') == {
        'unacked_key': '{app2}.unacked',
        'unacked_index_key': '{app2}.unacked_index',
        'unacked_mutex_key': '{app2}.unacked_mutex',
    }


def test_container_reads_queue_name_from_the_celery_section():
    container = AgentsContainer()
    container.config.from_dict({'celery': {'broker_url': BROKER, 'queue_name': 'app2'}})

    assert container.celery_client().conf.task_default_queue == '{app2}'


def test_container_defaults_when_the_ini_has_no_queue_name():
    container = AgentsContainer()
    container.config.from_dict({'celery': {'broker_url': BROKER}})

    assert container.celery_client().conf.task_default_queue == '{celery}'
