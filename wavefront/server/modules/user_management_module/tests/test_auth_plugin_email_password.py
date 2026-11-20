"""Unit tests for plugin email/password auth and health endpoint smoke."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import status
from flo_testing import add_async_cache_methods, add_async_token_methods

from user_management_module.controllers.auth_plugin_controller import (
    _handle_email_password_auth,
)
from user_management_module.utils.password_utils import hash_password


def _formatter():
    formatter = MagicMock()
    formatter.buildErrorResponse.side_effect = lambda msg: {'error': msg}
    formatter.buildSuccessResponse.side_effect = lambda data: {'data': data}
    return formatter


@pytest.mark.asyncio
async def test_plugin_email_password_requires_credentials():
    response = await _handle_email_password_auth(
        {},
        MagicMock(),
        _formatter(),
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
        MagicMock(),
        MagicMock(),
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_plugin_email_password_rejects_invalid_email():
    response = await _handle_email_password_auth(
        {'email': 'bad', 'password': 'x'},
        MagicMock(),
        _formatter(),
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
        MagicMock(),
        MagicMock(),
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_plugin_email_password_unknown_user():
    user_repository = AsyncMock()
    user_repository.find_one = AsyncMock(return_value=None)
    response = await _handle_email_password_auth(
        {'email': 'nobody@example.com', 'password': 'Secret@123'},
        MagicMock(),
        _formatter(),
        AsyncMock(),
        user_repository,
        AsyncMock(),
        MagicMock(),
        MagicMock(),
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_plugin_email_password_deleted_user():
    user_repository = AsyncMock()
    user_repository.find_one = AsyncMock(
        return_value=SimpleNamespace(deleted=True, email='d@example.com')
    )
    response = await _handle_email_password_auth(
        {'email': 'd@example.com', 'password': 'Secret@123'},
        MagicMock(),
        _formatter(),
        AsyncMock(),
        user_repository,
        AsyncMock(),
        MagicMock(),
        MagicMock(),
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_plugin_email_password_wrong_password():
    user_repository = AsyncMock()
    user_repository.find_one = AsyncMock(
        return_value=SimpleNamespace(
            deleted=False,
            email='u@example.com',
            password=hash_password('Correct@123'),
            id='uid',
        )
    )
    response = await _handle_email_password_auth(
        {'email': 'u@example.com', 'password': 'Wrong@123'},
        MagicMock(),
        _formatter(),
        AsyncMock(),
        user_repository,
        AsyncMock(),
        MagicMock(),
        MagicMock(),
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_plugin_email_password_success_mints_session():
    hashed = hash_password('Correct@123')
    user = SimpleNamespace(
        deleted=False, email='u@example.com', password=hashed, id='uid'
    )
    user_repository = AsyncMock()
    user_repository.find_one = AsyncMock(return_value=user)

    session_repository = AsyncMock()
    session_repository.find = AsyncMock(return_value=[])
    session_repository.delete_all = AsyncMock()
    created = SimpleNamespace(id='sid', user_id='uid', device_info='ua')
    session_repository.create = AsyncMock(return_value=created)

    user_service = AsyncMock()
    user_service.get_user_role_for_scope = AsyncMock(return_value='role')

    cache_manager = add_async_cache_methods(MagicMock())
    token_service = add_async_token_methods(MagicMock())
    token_service.create_token.return_value = 'jwt'
    token_service.token_expiry = 3600

    request = MagicMock()
    request.headers = {'User-Agent': 'ua'}

    response = await _handle_email_password_auth(
        {'email': 'u@example.com', 'password': 'Correct@123'},
        request,
        _formatter(),
        user_service,
        user_repository,
        session_repository,
        cache_manager,
        token_service,
    )
    assert response.status_code == status.HTTP_200_OK
    # The async entry points, so the handler can't fall back to blocking calls.
    token_service.create_token_async.assert_awaited_once()
    user_service.invalidate_user_sessions.assert_awaited_once_with('uid')


@pytest.mark.asyncio
async def test_plugin_email_password_clears_old_sessions_before_creating_new():
    # Reversing the order would delete the session this login just created.
    calls = []
    user = SimpleNamespace(
        deleted=False,
        email='u@example.com',
        password=hash_password('Correct@123'),
        id='uid',
    )
    user_repository = AsyncMock()
    user_repository.find_one = AsyncMock(return_value=user)

    session_repository = AsyncMock()
    created = SimpleNamespace(id='sid', user_id='uid', device_info='ua')

    async def _create(**kwargs):
        calls.append('create')
        return created

    session_repository.create = AsyncMock(side_effect=_create)

    user_service = AsyncMock()
    user_service.get_user_role_for_scope = AsyncMock(return_value='role')

    async def _invalidate(user_id):
        calls.append('invalidate')

    user_service.invalidate_user_sessions = AsyncMock(side_effect=_invalidate)

    token_service = add_async_token_methods(MagicMock())
    token_service.create_token.return_value = 'jwt'
    token_service.token_expiry = 3600
    request = MagicMock()
    request.headers = {'User-Agent': 'ua'}

    response = await _handle_email_password_auth(
        {'email': 'u@example.com', 'password': 'Correct@123'},
        request,
        _formatter(),
        user_service,
        user_repository,
        session_repository,
        add_async_cache_methods(MagicMock()),
        token_service,
    )

    assert response.status_code == status.HTTP_200_OK
    assert calls == ['invalidate', 'create']


@pytest.mark.asyncio
async def test_plugin_email_password_failed_signing_keeps_existing_sessions():
    # Signing happens before old sessions are revoked: a KMS or pool failure
    # must not leave the user logged out with no replacement session.
    from common_module.blocking_io import BlockingPoolBusyError

    user = SimpleNamespace(
        deleted=False,
        email='u@example.com',
        password=hash_password('Correct@123'),
        id='uid',
    )
    user_repository = AsyncMock()
    user_repository.find_one = AsyncMock(return_value=user)
    session_repository = AsyncMock()
    user_service = AsyncMock()
    user_service.get_user_role_for_scope = AsyncMock(return_value='role')
    token_service = add_async_token_methods(MagicMock())
    token_service.create_token_async = AsyncMock(
        side_effect=BlockingPoolBusyError('kms', 10.0)
    )
    token_service.token_expiry = 3600
    request = MagicMock()
    request.headers = {'User-Agent': 'ua'}

    with pytest.raises(BlockingPoolBusyError):
        await _handle_email_password_auth(
            {'email': 'u@example.com', 'password': 'Correct@123'},
            request,
            _formatter(),
            user_service,
            user_repository,
            session_repository,
            add_async_cache_methods(MagicMock()),
            token_service,
        )

    user_service.invalidate_user_sessions.assert_not_awaited()
    session_repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_plugin_email_password_refuses_an_account_disabled_during_login():
    """The user was read before bcrypt and signing; the account may be gone by now."""
    user = SimpleNamespace(
        deleted=False,
        email='u@example.com',
        password=hash_password('Correct@123'),
        id='uid',
    )
    user_repository = AsyncMock()
    user_repository.find_one = AsyncMock(return_value=user)
    session_repository = AsyncMock()
    user_service = AsyncMock()
    user_service.get_user_role_for_scope = AsyncMock(return_value='role')
    user_service.is_login_still_valid = AsyncMock(return_value=False)
    token_service = add_async_token_methods(MagicMock())
    token_service.create_token.return_value = 'jwt'
    token_service.token_expiry = 3600
    request = MagicMock()
    request.headers = {'User-Agent': 'ua'}

    response = await _handle_email_password_auth(
        {'email': 'u@example.com', 'password': 'Correct@123'},
        request,
        _formatter(),
        user_service,
        user_repository,
        session_repository,
        add_async_cache_methods(MagicMock()),
        token_service,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    user_service.invalidate_user_sessions.assert_not_awaited()
    session_repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_plugin_email_password_refuses_a_login_that_went_stale_after_insert():
    """A reset can commit between the first check and the insert; the second check catches it."""
    user = SimpleNamespace(
        deleted=False,
        email='u@example.com',
        password=hash_password('Correct@123'),
        id='uid',
    )
    user_repository = AsyncMock()
    user_repository.find_one = AsyncMock(return_value=user)
    session_repository = AsyncMock()
    session_repository.create = AsyncMock(return_value=SimpleNamespace(id='sid'))
    user_service = AsyncMock()
    user_service.get_user_role_for_scope = AsyncMock(return_value='role')
    user_service.is_login_still_valid = AsyncMock(return_value=True)
    user_service.confirm_new_session = AsyncMock(return_value=False)
    token_service = add_async_token_methods(MagicMock())
    token_service.create_token.return_value = 'jwt'
    token_service.token_expiry = 3600
    request = MagicMock()
    request.headers = {'User-Agent': 'ua'}

    response = await _handle_email_password_auth(
        {'email': 'u@example.com', 'password': 'Correct@123'},
        request,
        _formatter(),
        user_service,
        user_repository,
        session_repository,
        add_async_cache_methods(MagicMock()),
        token_service,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert b'jwt' not in response.body
    session_repository.create.assert_awaited_once()
    session_id, user_id, role_id = user_service.confirm_new_session.await_args.args
    assert (user_id, role_id) == ('uid', 'role')
    assert user_service.confirm_new_session.await_args.kwargs == {
        'password_hash': user.password
    }
    assert session_id == str(session_repository.create.await_args.kwargs['id'])
