"""Answers floware's legacy rules from its role tables.

This is the one place outside the default authorizer that asks "is this role
an admin": routes and handlers ask for an action instead.
"""

from __future__ import annotations

from authz_module import Principal
from common_module.common_container import CommonContainer
from common_module.feature.feature_flag import FeatureFlags
from db_repo_module.models.resource import Resource
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import Provide, inject

from user_management_module.constants.auth import SERVICE_AUTH_ROLE_ID
from user_management_module.user_container import UserContainer

# Looked up through the module on every call (not imported by name) so a test
# that patches user_utils.check_is_admin patches every decision.
from user_management_module.utils import user_utils


class FlowareLegacyResolver:
    async def is_admin(self, principal: Principal) -> bool:
        if principal.role_id is None:
            return False
        return await user_utils.check_is_admin(principal.role_id)

    async def is_manager(self, principal: Principal) -> bool:
        if principal.role_id is None:
            return False
        return await user_utils.check_is_manager(principal.role_id)

    async def can_write_datasource_rows(self, principal: Principal) -> bool:
        """TEMPORARY HACK until RBAC: admin, manager or editor by role name."""
        if principal.role_id is None:
            return False
        return await user_utils.can_write_datasource_rows(principal.role_id)

    async def is_console_user(self, principal: Principal) -> bool:
        return False

    async def has_resource_scope(self, principal: Principal, scope: str) -> bool:
        if principal.role_id is None:
            return False
        if principal.role_id == SERVICE_AUTH_ROLE_ID:
            return True
        return await _role_has_scope(principal.role_id, scope)

    def flag_enabled(self, flag: str) -> bool:
        return _flag_enabled(flag)


@inject
def _flag_enabled(
    flag: str,
    feature_flags: FeatureFlags = Provide[CommonContainer.feature_flags],
) -> bool:
    return feature_flags.enabled(flag)


@inject
async def _role_has_scope(
    role_id: str,
    scope: str,
    role_resource_repository: SQLAlchemyRepository[RoleResource] = Provide[
        UserContainer.role_resource_repository
    ],
    resource_repository: SQLAlchemyRepository[Resource] = Provide[
        UserContainer.resource_repository
    ],
) -> bool:
    grants = await role_resource_repository.find(role_id=role_id)
    for grant in grants:
        resource = await resource_repository.find_one(id=grant.resource_id)
        if resource is not None and resource.scope == scope:
            return True
    return False
