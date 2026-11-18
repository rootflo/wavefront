"""Login-path Redis calls: tolerant where a stale cache is safe, strict where it
would keep a session alive."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
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


async def test_lockout_cache_write_is_tolerant():
    cache = tolerant_cache()
    service = AccountLockoutService(MagicMock(), cache)

    await service._cache_user(user(), expiry=120)

    cache.try_aadd.assert_awaited_once()
    assert cache.try_aadd.await_args.kwargs == {'expiry': 120}


def logout_request(session_id='s1', user_id='u1'):
    return SimpleNamespace(
        state=SimpleNamespace(
            session=SimpleNamespace(session_id=session_id, user_id=user_id)
        )
    )


def formatter():
    return MagicMock(
        buildSuccessResponse=lambda data: {'data': data},
        buildErrorResponse=lambda error: {'error': error},
    )


async def test_logout_clears_the_cache_before_deleting_the_session():
    calls = []
    cache = MagicMock(
        aremove=AsyncMock(side_effect=lambda key: calls.append(('cache', key)) or True),
        try_aremove=AsyncMock(
            side_effect=lambda key: calls.append(('cache-again', key)) or True
        ),
    )
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
    assert calls == [
        ('cache', 'u1'),
        ('cache', get_session_cache_key('s1')),
        ('db', 's1'),
        ('cache-again', get_session_cache_key('s1')),
    ]


@pytest.mark.parametrize('fail_on', [0, 1])
async def test_logout_fails_cleanly_when_the_cache_cannot_be_cleared(fail_on):
    """503 with the DB session untouched, so a retry (or the old token after
    Redis recovers) still finds a consistent state."""
    outcomes = [True, True]
    outcomes[fail_on] = CacheUnavailableError('redis down')
    cache = MagicMock(aremove=AsyncMock(side_effect=outcomes), try_aremove=AsyncMock())
    sessions = MagicMock(delete_all=AsyncMock())

    response = await logout(
        request=logout_request(),
        session_repository=sessions,
        cache_manager=cache,
        response_formatter=formatter(),
    )

    assert response.status_code == 503
    sessions.delete_all.assert_not_awaited()
