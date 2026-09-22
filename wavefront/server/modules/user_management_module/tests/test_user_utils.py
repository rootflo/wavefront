"""Unit tests for user_utils admin/manager helpers and email normalization."""

import pytest

from user_management_module.constants.auth import SERVICE_AUTH_ROLE_ID
from user_management_module.utils.user_utils import (
    check_is_admin,
    check_is_manager,
    normalize_email,
)


def test_normalize_email_strips_and_lowercases():
    assert normalize_email('  User@Example.COM ') == 'user@example.com'


@pytest.mark.asyncio
async def test_check_is_admin_short_circuits_for_service_auth_role():
    assert await check_is_admin(SERVICE_AUTH_ROLE_ID) is True


@pytest.mark.asyncio
async def test_check_is_manager_service_auth_is_not_manager():
    assert await check_is_manager(SERVICE_AUTH_ROLE_ID) is False
