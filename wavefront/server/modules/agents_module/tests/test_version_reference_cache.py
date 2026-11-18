"""resolve_entity_current_version: async cache, database fallback when Redis fails."""

from unittest.mock import AsyncMock, Mock

import pytest

from agents_module.utils.version_reference_utils import resolve_entity_current_version


def make_cache(cached=None):
    cache = Mock()
    cache.try_aget_str = AsyncMock(return_value=cached)
    cache.try_aadd = AsyncMock(return_value=True)
    return cache


async def resolve(cache, repository):
    return await resolve_entity_current_version(
        cache_manager=cache,
        repository=repository,
        namespace='ns',
        name='flow',
        cache_key='current-version/ns/flow',
        ttl=30,
        not_found_message='Workflow not found: ns/flow',
    )


async def test_cache_hit_skips_the_database():
    repository = Mock(find_one=AsyncMock())

    assert await resolve(make_cache('4'), repository) == 4
    repository.find_one.assert_not_awaited()


async def test_cache_miss_reads_the_database_and_fills_the_cache():
    cache = make_cache(None)
    repository = Mock(find_one=AsyncMock(return_value=Mock(current_version=3)))

    assert await resolve(cache, repository) == 3
    cache.try_aadd.assert_awaited_once_with('current-version/ns/flow', '3', expiry=30)


async def test_unknown_entity_raises():
    repository = Mock(find_one=AsyncMock(return_value=None))

    with pytest.raises(ValueError, match='Workflow not found'):
        await resolve(make_cache(None), repository)


async def test_workflow_yaml_is_read_off_the_loop_and_cached():
    import threading

    from agents_module.services.workflow_inference_service import (
        WorkflowInferenceService,
    )
    from common_module.blocking_io import shutdown_blocking_io

    threads = []

    def read_file(_bucket, _key):
        threads.append(threading.get_ident())
        return b'arium: {}\n'

    service = object.__new__(WorkflowInferenceService)
    service.workflow_version_repository = None
    service.workflow_repository = None
    service.bucket_name = 'bucket'
    service.cloud_storage_manager = Mock(read_file=read_file)
    service.cache_manager = make_cache(None)
    try:
        yaml_content = await service.fetch_workflow_yaml('flow', 'ns', version=2)
    finally:
        shutdown_blocking_io()

    assert yaml_content == 'arium: {}\n'
    assert threads and threading.get_ident() not in threads
    service.cache_manager.try_aadd.assert_awaited_once()
