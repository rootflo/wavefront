"""Unit tests for plugin email/password auth and health endpoint smoke."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import status

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

    cache_manager = MagicMock()
    token_service = MagicMock()
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
    token_service.create_token.assert_called_once()
    cache_manager.add.assert_called()
