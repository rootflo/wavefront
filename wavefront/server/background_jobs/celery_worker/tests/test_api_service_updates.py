"""The worker follows floware's API-service update channel."""

import json
import threading
from unittest.mock import AsyncMock, MagicMock

import celery_worker.services as services
from api_services_module.utils.api_change_publisher import (
    REDIS_API_SERVICE_UPDATES_CHANNEL,
)


def test_updates_evict_the_service_so_it_reloads_on_next_use():
    messages = [
        {'type': 'subscribe', 'data': 1},
        {
            'type': 'message',
            'data': json.dumps({'service_id': 'osm-nominatim', 'operation': 'update'}),
        },
        {'type': 'message', 'data': 'not json'},
        {
            'type': 'message',
            'data': json.dumps({'service_id': 'old-service', 'operation': 'delete'}),
        },
    ]
    done = threading.Event()

    def listen():
        yield from messages
        done.set()

    pubsub = MagicMock()
    pubsub.listen.side_effect = listen
    cache = MagicMock()
    cache.subscribe.return_value = pubsub
    proxy = MagicMock()

    services._listen_for_api_service_updates(cache, proxy)

    assert done.wait(timeout=5)
    cache.subscribe.assert_called_once_with(
        channels=[REDIS_API_SERVICE_UPDATES_CHANNEL]
    )
    assert [c.args[0] for c in proxy.remove_service.call_args_list] == [
        'osm-nominatim',
        'old-service',
    ]


def test_all_api_services_load_once_at_startup(monkeypatch):
    service = MagicMock(id='osm-nominatim')
    registry = MagicMock()
    registry.load_from_db = AsyncMock()
    registry.get_all_services.return_value = {'osm-nominatim': service}
    proxy = MagicMock()
    container = MagicMock()
    container.api_services.initialized_service_registry.return_value = registry
    container.api_services.api_proxy.return_value = proxy
    monkeypatch.setattr(services, '_services', MagicMock(name='WorkerServices'))
    monkeypatch.setattr(services, '_container', container)
    monkeypatch.setattr(services, '_api_services_loaded', False)

    services.load_api_services()
    services.load_api_services()  # worker_ready and worker_process_init may both fire

    registry.load_from_db.assert_awaited_once()
    proxy.auth_manager.register_service_auth.assert_called_once_with(service)


def test_a_failed_startup_load_does_not_stop_the_worker(monkeypatch):
    registry = MagicMock()
    registry.load_from_db = AsyncMock(side_effect=RuntimeError('db down'))
    container = MagicMock()
    container.api_services.initialized_service_registry.return_value = registry
    monkeypatch.setattr(services, '_services', MagicMock(name='WorkerServices'))
    monkeypatch.setattr(services, '_container', container)
    monkeypatch.setattr(services, '_api_services_loaded', False)

    services.load_api_services()  # logs a warning; services still load on first use
