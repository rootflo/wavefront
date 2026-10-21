"""Configuration of the publishing Celery app. No broker is contacted."""

import celery
from dependency_injector import providers

from agents_module.agents_container import AgentsContainer
from agents_module.utils.celery_client import build_celery_client
from agents_module.utils.celery_settings import CeleryProducerSettings

BROKER = 'redis://localhost:6379/0'


def test_does_not_become_the_current_app():
    """The default set_as_current=True replaced the worker's own app."""
    before = celery.current_app

    app = build_celery_client(broker_url=BROKER)

    assert app is not celery.current_app
    assert celery.current_app is before


def test_publishes_to_the_hash_tagged_queue():
    """Must match task_default_queue in celery_worker/celery_app.py."""
    assert build_celery_client(broker_url=BROKER).conf.task_default_queue == '{celery}'


def test_broker_socket_timeouts_are_set():
    options = build_celery_client(broker_url=BROKER).conf.broker_transport_options

    assert options['socket_timeout'] > 0
    assert options['socket_connect_timeout'] > 0


def test_broker_url_comes_from_the_argument(monkeypatch):
    """A CELERY_BROKER_URL in the environment would win over the argument."""
    monkeypatch.delenv('CELERY_BROKER_URL', raising=False)

    app = build_celery_client(broker_url='redis://elsewhere:6380/2')

    assert app.conf.broker_url == 'redis://elsewhere:6380/2'


def test_container_provides_one_app_per_process():
    assert isinstance(AgentsContainer.celery_client, providers.Singleton)


def test_socket_timeout_comes_from_the_settings():
    settings = CeleryProducerSettings(broker_socket_timeout_seconds='0.5')

    options = build_celery_client(
        BROKER, settings=settings
    ).conf.broker_transport_options

    assert options == {'socket_timeout': 0.5, 'socket_connect_timeout': 0.5}


def test_container_reads_the_knobs_from_the_celery_config_section():
    """config.ini -> container -> settings -> the service that uses them."""
    container = AgentsContainer()
    container.config.from_dict(
        {
            'celery': {
                'broker_url': BROKER,
                'max_queue_depth': '250',
                'queue_depth_cache_ttl_seconds': '0.5',
                'queue_depth_warn_ratio': '0.9',
                'backpressure_retry_after_seconds': '45',
                'broker_socket_timeout_seconds': '3.0',
            }
        }
    )

    settings = container.celery_settings()

    assert settings == CeleryProducerSettings(250, 0.5, 0.9, 45, 3.0)
    assert container.celery_client().conf.broker_transport_options == {
        'socket_timeout': 3.0,
        'socket_connect_timeout': 3.0,
    }


def test_container_defaults_the_knobs_an_ini_does_not_define():
    """The worker's ini defines only the socket timeout."""
    container = AgentsContainer()
    container.config.from_dict(
        {'celery': {'broker_url': BROKER, 'broker_socket_timeout_seconds': '4'}}
    )

    assert container.celery_settings() == CeleryProducerSettings(
        broker_socket_timeout_seconds=4.0
    )


def test_container_passes_queue_name_and_settings_together():
    import celery

    before = celery.current_app
    container = AgentsContainer()
    container.config.from_dict(
        {
            'celery': {
                'broker_url': BROKER,
                'queue_name': 'app2',
                'broker_socket_timeout_seconds': '3.0',
            }
        }
    )

    app = container.celery_client()

    assert app.conf.task_default_queue == '{app2}'
    assert app.conf.broker_transport_options['socket_timeout'] == 3.0
    assert celery.current_app is before
