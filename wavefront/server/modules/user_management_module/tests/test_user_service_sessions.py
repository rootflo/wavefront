"""Unit tests for UserService.invalidate_user_sessions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest
from db_repo_module.cache.cache_manager import CacheUnavailableError
from flo_testing import add_async_cache_methods
from user_management_module.constants.cache import get_session_cache_key
from user_management_module.services.user_service import UserService


def _service(sessions, cache_manager):
    session_repository = MagicMock()
    session_repository.find = AsyncMock(return_value=sessions)
    session_repository.delete_all = AsyncMock()
    service = UserService(
        user_repository=MagicMock(),
        user_role_repository=MagicMock(),
        session_repository=session_repository,
        resource_repository=MagicMock(),
        cache_manager=cache_manager,
        user_group_member_repository=MagicMock(),
    )
    return service, session_repository


@pytest.mark.asyncio
async def test_invalidate_user_sessions_clears_every_cache_key_then_rows():
    cache_manager = add_async_cache_methods(MagicMock())
    sessions = [SimpleNamespace(id='s1'), SimpleNamespace(id='s2')]
    service, session_repository = _service(sessions, cache_manager)
    order = []
    cache_manager.remove.side_effect = lambda key: order.append(('cache', key))

    async def record_delete(**_kwargs):
        order.append(('db', None))

    session_repository.delete_all.side_effect = record_delete

    await service.invalidate_user_sessions('uid')

    cache_manager.remove.assert_any_call(get_session_cache_key('s1'))
    cache_manager.remove.assert_any_call(get_session_cache_key('s2'))
    cache_manager.remove.assert_any_call('uid')
    session_repository.delete_all.assert_awaited_once_with(user_id='uid')
    # All three cache deletes happen before the rows go.
    assert [kind for kind, _ in order] == ['cache', 'cache', 'cache', 'db']


@pytest.mark.asyncio
async def test_invalidate_user_sessions_keeps_rows_when_cache_remove_fails():
    # A failed cache delete must surface before the DB rows go, so the caller
    # fails instead of reporting success while the cached session still works.
    cache_manager = MagicMock()
    cache_manager.aremove = AsyncMock(side_effect=CacheUnavailableError('redis down'))
    service, session_repository = _service([SimpleNamespace(id='s1')], cache_manager)

    with pytest.raises(CacheUnavailableError):
        await service.invalidate_user_sessions('uid')

    session_repository.delete_all.assert_not_awaited()
