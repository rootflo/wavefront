"""Unit tests for user_utils admin/manager helpers and email normalization."""

from types import SimpleNamespace

import pytest

from user_management_module.constants.auth import SERVICE_AUTH_ROLE_ID
from user_management_module.utils.user_utils import (
    can_write_datasource_rows,
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


class _Roles:
    """Role repository stand-in: find_one(id=...) returns a role with that name."""

    def __init__(self, name):
        self.name = name

    async def find_one(self, id):
        return SimpleNamespace(name=self.name) if self.name else None


# TEMPORARY HACK until RBAC: admin, manager and editor may update/delete datasource rows.
@pytest.mark.asyncio
@pytest.mark.parametrize(
    'role_name, allowed',
    [
        ('admin', True),
        ('manager', True),
        ('editor', True),
        ('viewer', False),
        ('underwriter', False),
        (None, False),
    ],
)
async def test_can_write_datasource_rows_by_role_name(role_name, allowed):
    assert await can_write_datasource_rows('role-id', _Roles(role_name)) is allowed


@pytest.mark.asyncio
async def test_can_write_datasource_rows_allows_service_auth():
    assert await can_write_datasource_rows(SERVICE_AUTH_ROLE_ID) is True
