"""Login-path Redis calls: tolerant where a stale cache is safe, strict where it
would keep a session alive."""

import json
from types import SimpleNamespace

from authz_module import user_principal
from unittest.mock import AsyncMock, MagicMock

from flo_testing import add_async_cache_methods
from db_repo_module.cache.cache_manager import CacheUnavailableError
from user_management_module.constants.cache import (
    get_session_cache_key,
    user_by_id_cache_key,
)
from user_management_module.controllers.auth_controller import logout
from user_management_module.services.account_inactivity_service import (
    AccountInactivityService,
)
from user_management_module.services.account_lockout_service import (
    AccountLockoutService,
)


def tolerant_cache():
    cache = MagicMock()
    cache.try_aadd = AsyncMock(return_value=True)
    return cache


def user(user_id='u1'):
    return SimpleNamespace(
        id=user_id, email='a@b.c', to_dict=lambda: {'id': user_id, 'email': 'a@b.c'}
    )


async def test_last_login_cache_write_is_tolerant():
    cache = tolerant_cache()
    repository = MagicMock(find_one_and_update=AsyncMock(return_value=user()))
    service = AccountInactivityService(repository, cache)

    await service.update_last_login(user())

    cache.try_aadd.assert_awaited_once()
    key, value = cache.try_aadd.await_args.args
    assert key == user_by_id_cache_key('u1')
    assert json.loads(value)['id'] == 'u1'


async def test_last_login_completes_when_the_cache_write_fails():
    cache = tolerant_cache()
    cache.try_aadd.return_value = False  # Redis rejected the best-effort write
    repository = MagicMock(find_one_and_update=AsyncMock(return_value=user()))
    service = AccountInactivityService(repository, cache)

    await service.update_last_login(user())

    repository.find_one_and_update.assert_awaited_once()


async def test_lockout_completes_when_the_cache_write_fails():
    cache = tolerant_cache()
    cache.try_aadd.return_value = False
    service = AccountLockoutService(MagicMock(), cache)

    await service._cache_user(user(), expiry=120)  # must not raise

    cache.try_aadd.assert_awaited_once()


async def test_lockout_cache_write_is_tolerant():
    cache = tolerant_cache()
    service = AccountLockoutService(MagicMock(), cache)

    await service._cache_user(user(), expiry=120)

    cache.try_aadd.assert_awaited_once()
    assert cache.try_aadd.await_args.kwargs == {'expiry': 120}


def logout_request(session_id='s1', user_id='u1'):
    return SimpleNamespace(
        state=SimpleNamespace(principal=user_principal(user_id, session_id=session_id))
    )


def formatter():
    return MagicMock(
        buildSuccessResponse=lambda data: {'data': data},
        buildErrorResponse=lambda error: {'error': error},
    )


async def test_logout_invalidates_around_the_session_delete():
    calls = []
    cache = add_async_cache_methods(MagicMock())
    cache.remove.side_effect = lambda key: calls.append(('cache', key))
    sessions = MagicMock(
        delete_all=AsyncMock(side_effect=lambda **kw: calls.append(('db', kw['id'])))
    )

    response = await logout(
        request=logout_request(),
        session_repository=sessions,
        cache_manager=cache,
        response_formatter=formatter(),
    )

    assert response.status_code == 200
    session_key = get_session_cache_key('s1')
    assert calls == [
        ('cache', 'u1'),
        ('cache', session_key),
        ('db', 's1'),
        ('cache', 'u1'),
        ('cache', session_key),
    ]


async def test_logout_fails_cleanly_when_the_cache_cannot_be_invalidated():
    """503 with the DB session untouched, so a retry (or the old token after
    Redis recovers) still finds a consistent state."""
    cache = add_async_cache_methods(MagicMock())
    cache.remove.side_effect = CacheUnavailableError('redis down')
    sessions = MagicMock(delete_all=AsyncMock())

    response = await logout(
        request=logout_request(),
        session_repository=sessions,
        cache_manager=cache,
        response_formatter=formatter(),
    )

    assert response.status_code == 503
    sessions.delete_all.assert_not_awaited()
