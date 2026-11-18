"""ApiServicesManager: service definitions are read and written off the event loop,
with the Redis cache tolerant of failures."""

import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from api_services_module.core.manager import ApiServicesManager
from common_module.blocking_io import shutdown_blocking_io

YAML = 'id: acme\n'


@pytest.fixture(autouse=True)
def fresh_pools():
    yield
    shutdown_blocking_io()


class Storage:
    def __init__(self):
        self.threads = []

    def read_file(self, bucket_name, file_path):
        self.threads.append(threading.get_ident())
        return YAML.encode()

    def save_small_file(self, **_kwargs):
        self.threads.append(threading.get_ident())

    def delete_file(self, **_kwargs):
        self.threads.append(threading.get_ident())


def make_manager(cache, storage):
    return ApiServicesManager(
        api_services_repository=AsyncMock(),
        cloud_storage_manager=storage,
        cache_manager=cache,
        config={'storage': {'application_bucket': 'bucket'}},
    )


def make_cache(cached=None):
    cache = Mock()
    cache.try_aget_str = AsyncMock(return_value=cached)
    cache.try_aadd = AsyncMock(return_value=True)
    cache.aadd = AsyncMock(return_value=True)
    cache.try_aremove = AsyncMock(return_value=True)
    return cache


async def test_cache_hit_skips_storage():
    storage = Storage()
    manager = make_manager(make_cache(YAML), storage)

    assert await manager.fetch_service_def(SimpleNamespace(id='acme')) == YAML
    assert storage.threads == []


async def test_cache_miss_reads_storage_off_the_loop():
    storage = Storage()
    manager = make_manager(make_cache(None), storage)

    assert await manager.fetch_service_def(SimpleNamespace(id='acme')) == YAML
    assert storage.threads and threading.get_ident() not in storage.threads


async def test_writes_and_deletes_run_off_the_loop_and_update_the_cache():
    storage, cache = Storage(), make_cache()
    manager = make_manager(cache, storage)

    await manager.create_api_service('acme', YAML)
    await manager.update_api_service('acme', YAML)
    await manager.delete_api_service('acme')

    assert len(storage.threads) == 3
    assert threading.get_ident() not in storage.threads
    cache.try_aadd.assert_awaited_once()  # create: a new key, tolerant
    cache.aadd.assert_awaited_once()  # update: replaces a cached old version, strict
    cache.try_aremove.assert_awaited_once_with('api_services/acme.yaml')


async def test_busy_pool_on_delete_leaves_everything_in_place(monkeypatch):
    """A 503 on delete must leave a retryable state: row, file and cache intact."""
    from api_services_module.core import manager as manager_module
    from common_module.blocking_io import BlockingPoolBusyError

    async def busy(*_args, **_kwargs):
        raise BlockingPoolBusyError('storage', 10.0)

    monkeypatch.setattr(manager_module, 'run_in_pool', busy)
    cache = make_cache()
    manager = make_manager(cache, Storage())

    with pytest.raises(BlockingPoolBusyError):
        await manager.delete_api_service('acme')

    manager.api_services_repository.delete_all.assert_not_awaited()
    cache.try_aremove.assert_not_awaited()


async def test_failed_cache_write_on_update_is_raised():
    """The reload after an update reads the cache first, so a silently failed
    write would keep serving the old definition: surface it (a 503)."""
    from db_repo_module.cache.cache_manager import CacheUnavailableError

    cache = make_cache()
    cache.aadd = AsyncMock(side_effect=CacheUnavailableError('down'))
    manager = make_manager(cache, Storage())

    with pytest.raises(CacheUnavailableError):
        await manager.update_api_service('acme', YAML)


def ordered_manager(storage_error=None, db_error=None):
    calls = []

    class OrderedStorage(Storage):
        def delete_file(self, **_kwargs):
            calls.append('storage')
            if storage_error:
                raise storage_error

    cache = make_cache()
    cache.try_aremove = AsyncMock(side_effect=lambda _key: calls.append('cache'))
    manager = make_manager(cache, OrderedStorage())

    async def delete_all(**_kwargs):
        calls.append('db')
        if db_error:
            raise db_error

    manager.api_services_repository.delete_all = AsyncMock(side_effect=delete_all)
    return manager, calls


async def test_delete_order_is_storage_then_db_then_cache():
    manager, calls = ordered_manager()

    await manager.delete_api_service('acme')

    assert calls == ['storage', 'db', 'cache']


async def test_missing_file_does_not_block_the_delete():
    """GCS and Azure raise when the file is already gone; the row must still go,
    or it could never be deleted."""
    manager, calls = ordered_manager(storage_error=Exception('blob not found'))

    await manager.delete_api_service('acme')

    assert calls == ['storage', 'db', 'cache']


async def test_db_failure_after_storage_leaves_the_cache_alone():
    manager, calls = ordered_manager(db_error=RuntimeError('db down'))

    with pytest.raises(RuntimeError):
        await manager.delete_api_service('acme')

    assert calls == ['storage', 'db']
