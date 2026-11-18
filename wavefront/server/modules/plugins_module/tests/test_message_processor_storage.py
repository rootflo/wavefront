"""Message processor YAML: storage calls run off the event loop, reads are cached.

Every write goes through MessageProcessorService, so it also keeps the cache
current. Redis failures only cost a storage read and are never raised.
"""

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
    def __init__(self):
        self.data = {}
        self.aget_str = AsyncMock(side_effect=self._get)
        self.aadd = AsyncMock(side_effect=self._add)
        self.aremove = AsyncMock(side_effect=self._remove)

    async def _get(self, key, default=None, **_kwargs):
        return self.data.get(key, default)

    async def _add(self, key, value, expiry=3600, **_kwargs):
        self.data[key] = value
        return True

    async def _remove(self, key, **_kwargs):
        return self.data.pop(key, None) is not None


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
    cache.aget_str.side_effect = CacheUnavailableError('down')
    cache.aadd.side_effect = CacheUnavailableError('down')
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
    assert storage.count('read_file') == 1  # the update refreshed the cache
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


async def test_failed_cache_delete_does_not_fail_the_delete():
    storage, cache = FakeStorage(), FakeCache()
    cache.aremove.side_effect = CacheUnavailableError('down')
    service = make_service(storage, cache)

    assert await service.delete_message_processor('p1') is True
    assert storage.count('delete_file') == 1


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
    cache.aget_str.assert_not_awaited()
    cache.aadd.assert_not_awaited()


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
