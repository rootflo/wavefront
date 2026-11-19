"""ApiServicesManager: service definitions are read and written off the event loop
through the generation-checked cache (reads tolerant, writes strict)."""

import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from api_services_module.core.manager import ApiServicesManager
from db_repo_module.cache.cache_manager import CacheUnavailableError
from flo_testing import add_async_cache_methods
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
    cache = add_async_cache_methods(Mock())
    cache.get_str.return_value = cached
    return cache


async def test_cache_hit_skips_storage():
    storage = Storage()
    manager = make_manager(make_cache(YAML), storage)

    assert await manager.fetch_service_def(SimpleNamespace(id='acme')) == YAML
    assert storage.threads == []


async def test_cache_miss_reads_storage_off_the_loop_and_fills():
    storage, cache = Storage(), make_cache(None)
    manager = make_manager(cache, storage)

    assert await manager.fetch_service_def(SimpleNamespace(id='acme')) == YAML
    assert storage.threads and threading.get_ident() not in storage.threads
    cache.add.assert_called_once_with('api_services/acme.yaml', YAML, 3600)


async def test_writes_and_deletes_run_off_the_loop_and_invalidate():
    storage, cache = Storage(), make_cache()
    manager = make_manager(cache, storage)

    await manager.create_api_service('acme', YAML)
    await manager.update_api_service('acme', YAML)
    await manager.delete_api_service('acme')

    assert len(storage.threads) == 3
    assert threading.get_ident() not in storage.threads
    # Each write invalidates before and after; none writes the value itself.
    assert cache.remove.call_count == 6
    cache.add.assert_not_called()


async def test_redis_down_stops_an_update_before_anything_changes():
    """The reload after an update reads through the cache, so with Redis down
    the update must fail (503) rather than leave the old definition cached."""
    storage, cache = Storage(), make_cache()
    cache.remove.side_effect = CacheUnavailableError('down')
    manager = make_manager(cache, storage)

    with pytest.raises(CacheUnavailableError):
        await manager.update_api_service('acme', YAML)

    assert storage.threads == []
    manager.api_services_repository.find_one_and_update.assert_not_awaited()


async def test_busy_pool_on_delete_leaves_everything_in_place(monkeypatch):
    """A 503 on delete must leave a retryable state: row and file intact."""
    from api_services_module.core import manager as manager_module
    from common_module.blocking_io import BlockingPoolBusyError

    async def busy(*_args, **_kwargs):
        raise BlockingPoolBusyError('storage', 10.0)

    monkeypatch.setattr(manager_module, 'run_in_pool', busy)
    manager = make_manager(make_cache(), Storage())

    with pytest.raises(BlockingPoolBusyError):
        await manager.delete_api_service('acme')

    manager.api_services_repository.delete_all.assert_not_awaited()


def ordered_manager(storage_error=None, db_error=None):
    calls = []

    class OrderedStorage(Storage):
        def delete_file(self, **_kwargs):
            calls.append('storage')
            if storage_error:
                raise storage_error

    cache = make_cache()
    cache.remove.side_effect = lambda _key: calls.append('cache')
    manager = make_manager(cache, OrderedStorage())

    async def delete_all(**_kwargs):
        calls.append('db')
        if db_error:
            raise db_error

    manager.api_services_repository.delete_all = AsyncMock(side_effect=delete_all)
    return manager, calls


async def test_delete_order_is_invalidate_storage_db_invalidate():
    manager, calls = ordered_manager()

    await manager.delete_api_service('acme')

    assert calls == ['cache', 'storage', 'db', 'cache']


async def test_missing_file_does_not_block_the_delete():
    """GCS and Azure raise when the file is already gone; the row must still go,
    or it could never be deleted."""
    manager, calls = ordered_manager(storage_error=Exception('blob not found'))

    await manager.delete_api_service('acme')

    assert calls == ['cache', 'storage', 'db', 'cache']


async def test_db_failure_after_storage_still_invalidates():
    manager, calls = ordered_manager(db_error=RuntimeError('db down'))

    with pytest.raises(RuntimeError):
        await manager.delete_api_service('acme')

    assert calls == ['cache', 'storage', 'db', 'cache']
