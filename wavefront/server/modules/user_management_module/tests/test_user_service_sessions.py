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
    # Every key is invalidated before the rows go, and again after (so a fill
    # that raced the revocation can't revive a session).
    assert [kind for kind, _ in order] == ['cache'] * 3 + ['db'] + ['cache'] * 3


@pytest.mark.asyncio
async def test_invalidate_user_sessions_keeps_rows_when_cache_remove_fails():
    # A failed cache delete must surface before the DB rows go, so the caller
    # fails instead of reporting success while the cached session still works.
    cache_manager = add_async_cache_methods(MagicMock())
    cache_manager.remove.side_effect = CacheUnavailableError('redis down')
    service, session_repository = _service([SimpleNamespace(id='s1')], cache_manager)

    with pytest.raises(CacheUnavailableError):
        await service.invalidate_user_sessions('uid')

    session_repository.delete_all.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'user, role, expected',
    [
        (SimpleNamespace(deleted=False, password='h1'), 'r1', True),
        (SimpleNamespace(deleted=True, password='h1'), 'r1', False),  # disabled
        (SimpleNamespace(deleted=False, password='h2'), 'r1', False),  # new password
        (SimpleNamespace(deleted=False, password='h1'), 'r2', False),  # role changed
        (None, 'r1', False),  # gone
    ],
    ids=['unchanged', 'disabled', 'password-changed', 'role-changed', 'gone'],
)
async def test_login_is_only_valid_while_the_user_is_unchanged(user, role, expected):
    service, _ = _service([], add_async_cache_methods(MagicMock()))
    service.user_repository = MagicMock(find_one=AsyncMock(return_value=user))
    service.get_user_role_for_scope = AsyncMock(return_value=role)

    assert (
        await service.is_login_still_valid('uid', 'r1', password_hash='h1') is expected
    )


@pytest.mark.asyncio
async def test_confirm_new_session_keeps_the_row_while_the_login_is_valid():
    cache_manager = add_async_cache_methods(MagicMock())
    service, session_repository = _service([], cache_manager)
    service.is_login_still_valid = AsyncMock(return_value=True)

    assert await service.confirm_new_session('s1', 'uid', 'r1', password_hash='h1')

    service.is_login_still_valid.assert_awaited_once_with('uid', 'r1', 'h1')
    session_repository.delete_all.assert_not_awaited()
    cache_manager.remove.assert_not_called()


@pytest.mark.asyncio
async def test_confirm_new_session_drops_the_row_when_the_login_went_stale():
    # A reset that committed after the first check but before the insert has
    # already revoked sessions, so the new row is removed here instead.
    cache_manager = add_async_cache_methods(MagicMock())
    service, session_repository = _service([], cache_manager)
    service.is_login_still_valid = AsyncMock(return_value=False)

    assert not await service.confirm_new_session('s1', 'uid', 'r1', password_hash='h1')

    session_repository.delete_all.assert_awaited_once_with(id='s1')
    cache_manager.remove.assert_any_call(get_session_cache_key('s1'))
