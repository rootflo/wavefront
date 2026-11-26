"""Message processor YAML: storage calls run off the event loop, reads are cached.

Reads go through the generation-checked cache and fall back to storage if
Redis fails; writes invalidate strictly, so with Redis down they fail before
storage changes.
"""

import contextlib
import threading
from unittest.mock import AsyncMock, Mock

import pytest

from common_module.blocking_io import shutdown_blocking_io
from db_repo_module.cache.cache_manager import CacheUnavailableError
from plugins_module.services.message_processor_service import MessageProcessorService

VALID_YAML = """
type: javascript
description: Echo the input
function:
  code: 'export default (input) => input'
input_schema:
  required: [message]
  properties:
    message: {type: string}
"""


@pytest.fixture(autouse=True)
def fresh_pools():
    yield
    shutdown_blocking_io()


class FakeStorage:
    """Records which thread each call ran on."""

    def __init__(self, content: str = VALID_YAML):
        self.files = {'message_processors/v1/p1.yaml': content.encode()}
        self.calls = []

    def _record(self, name):
        self.calls.append((name, threading.get_ident()))

    def read_file(self, bucket, key):
        self._record('read_file')
        return self.files[key]

    def save_small_file(self, file_content, bucket_name, key, disable_cache=False):
        self._record('save_small_file')
        self.files[key] = file_content

    def delete_file(self, bucket, key):
        self._record('delete_file')
        self.files.pop(key, None)

    def count(self, name):
        return sum(1 for call, _ in self.calls if call == name)


class FakeCache:
    """read_through / invalidating with CacheManager's failure semantics:
    reads fall back to the loader, writes are strict before the change."""

    def __init__(self):
        self.data = {}
        self.down = False
        self.read_through = AsyncMock(side_effect=self._read_through)

    async def _read_through(self, key, loader, *, ttl):
        if self.down:
            return await loader()
        if key in self.data:
            return self.data[key]
        value = await loader()
        if value is not None:
            self.data[key] = value
        return value

    @contextlib.asynccontextmanager
    async def invalidating(self, *keys):
        if self.down:
            raise CacheUnavailableError('down')
        for key in keys:
            self.data.pop(key, None)
        yield
        for key in keys:
            self.data.pop(key, None)


def make_service(storage, cache=None):
    repository = AsyncMock()
    repository.find_one = AsyncMock(return_value=Mock(source='p1.yaml'))
    return MessageProcessorService(
        cloud_storage_manager=storage,
        message_processor_repository=repository,
        hermes_url='http://hermes',
        bucket_name='bucket',
        cache_manager=cache,
    )


def processor():
    return Mock(source='p1.yaml')


async def test_read_runs_off_the_loop_and_is_cached():
    storage, cache = FakeStorage(), FakeCache()
    service = make_service(storage, cache)

    first = await service.get_message_processor_yaml_content(processor())
    second = await service.get_message_processor_yaml_content(processor())

    assert first == second == VALID_YAML
    assert storage.count('read_file') == 1
    assert threading.get_ident() not in [thread for _, thread in storage.calls]


async def test_redis_down_on_read_falls_back_to_storage():
    storage, cache = FakeStorage(), FakeCache()
    cache.down = True
    service = make_service(storage, cache)

    assert await service.get_message_processor_yaml_content(processor()) == VALID_YAML
    assert storage.count('read_file') == 1


async def test_update_replaces_the_cached_yaml():
    storage, cache = FakeStorage(), FakeCache()
    service = make_service(storage, cache)
    await service.get_message_processor_yaml_content(processor())
    updated = VALID_YAML.replace('Echo the input', 'Echo, updated')

    await service.save_message_processor_yaml(
        yaml_content=updated, file_path='message_processors/v1/p1.yaml'
    )

    assert await service.get_message_processor_yaml_content(processor()) == updated
    assert storage.count('read_file') == 2  # the update invalidated the cache
    assert threading.get_ident() not in [thread for _, thread in storage.calls]


async def test_invalid_yaml_is_rejected_before_storage():
    storage = FakeStorage()
    service = make_service(storage, FakeCache())

    with pytest.raises(ValueError):
        await service.save_message_processor_yaml(
            yaml_content='type: x', file_path='message_processors/v1/p1.yaml'
        )

    assert storage.count('save_small_file') == 0


async def test_delete_removes_the_file_and_the_cached_yaml():
    storage, cache = FakeStorage(), FakeCache()
    service = make_service(storage, cache)
    await service.get_message_processor_yaml_content(processor())

    assert await service.delete_message_processor('p1') is True

    assert storage.count('delete_file') == 1
    assert cache.data == {}
    assert threading.get_ident() not in [thread for _, thread in storage.calls]


async def test_redis_down_stops_writes_before_storage_changes():
    """Strict invalidation: a 503 with nothing changed, never a stale cache."""
    storage, cache = FakeStorage(), FakeCache()
    cache.down = True
    service = make_service(storage, cache)

    with pytest.raises(CacheUnavailableError):
        await service.delete_message_processor('p1')
    with pytest.raises(CacheUnavailableError):
        await service.save_message_processor_yaml(
            yaml_content=VALID_YAML, file_path='message_processors/v1/p1.yaml'
        )

    assert storage.count('delete_file') == 0
    assert storage.count('save_small_file') == 0


async def test_zero_seconds_turns_the_cache_off():
    storage, cache = FakeStorage(), FakeCache()
    service = MessageProcessorService(
        cloud_storage_manager=storage,
        message_processor_repository=AsyncMock(),
        hermes_url='http://hermes',
        bucket_name='bucket',
        cache_manager=cache,
        yaml_cache_seconds='0',
    )

    await service.get_message_processor_yaml_content(processor())
    await service.get_message_processor_yaml_content(processor())

    assert storage.count('read_file') == 2
    cache.read_through.assert_not_awaited()


def test_cache_seconds_setting():
    def build(value):
        return MessageProcessorService(
            cloud_storage_manager=FakeStorage(),
            message_processor_repository=AsyncMock(),
            hermes_url='http://hermes',
            yaml_cache_seconds=value,
        )

    assert build(None).yaml_cache_seconds == 3600
    assert build('').yaml_cache_seconds == 3600
    assert build('120').yaml_cache_seconds == 120
    with pytest.raises(ValueError):
        build('-1')


async def test_works_without_a_cache():
    storage = FakeStorage()
    service = make_service(storage)

    await service.get_message_processor_yaml_content(processor())
    await service.get_message_processor_yaml_content(processor())

    assert storage.count('read_file') == 2
