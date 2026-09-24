from typing import Any, List, Optional, cast
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.user import User
from db_repo_module.models.user_group_member import UserGroupMember
from db_repo_module.models.user_group_role import UserGroupRole
from db_repo_module.models.user_role import UserRole
from db_repo_module.models.session import Session
from db_repo_module.models.resource import Resource, ResourceScope
from db_repo_module.models.role import Role
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.cache.cache_manager import CacheManager
from sqlalchemy import select, Result, and_, or_, func
from user_management_module.constants.auth import ADMIN_ROLE_NAME
from user_management_module.constants.cache import USER_DATA_PATTERN
from user_management_module.constants.cache import get_session_cache_key
from common_module.response_formatter import ResponseFormatter
from common_module.log.logger import logger
from user_management_module.utils.password_utils import hash_password
from user_management_module.models.user_schema import NewUser
from fastapi.responses import JSONResponse
from fastapi import status


class UserService:
    def __init__(
        self,
        user_repository: SQLAlchemyRepository[User],
        user_role_repository: SQLAlchemyRepository[UserRole],
        session_repository: SQLAlchemyRepository[Session],
        resource_repository: SQLAlchemyRepository[Resource],
        cache_manager: CacheManager,
        user_group_member_repository: SQLAlchemyRepository[UserGroupMember],
    ):
        self.user_repository = user_repository
        self.user_role_repository = user_role_repository
        self.session_repository = session_repository
        self.resource_repository = resource_repository
        self.cache_manager = cache_manager
        self.user_group_member_repository = user_group_member_repository

    @staticmethod
    def effective_role_ids(user_id: str):
        """Roles a user holds directly plus roles granted by their groups.

        The single definition of "which roles does this user have". Filtering on
        it rather than joining `user_role` is what makes group membership count
        everywhere a direct assignment does.

        A group with no roles contributes no rows, so members of an empty group
        simply keep their direct roles. The `User.deleted` guard sits inside both
        branches so every caller inherits it.
        """
        direct = (
            select(UserRole.role_id)
            .join(User, User.id == UserRole.user_id)
            .where(UserRole.user_id == user_id, User.deleted.is_(False))
        )
        via_group = (
            select(UserGroupRole.role_id)
            .join(
                UserGroupMember,
                UserGroupMember.group_id == UserGroupRole.group_id,
            )
            .join(User, User.id == UserGroupMember.user_id)
            .where(UserGroupMember.user_id == user_id, User.deleted.is_(False))
        )
        return direct.union(via_group)

    async def resolve_assignment_role_ids(
        self,
        role_ids: Optional[List[str]] = None,
        group_ids: Optional[List[str]] = None,
    ) -> set[str]:
        """Every role a user would hold given these direct roles and groups.

        Used before the user exists (creation) or before an assignment is
        committed, where `effective_role_ids` has nothing to read yet. Because a
        group may carry no roles, membership alone can contribute nothing here --
        which is exactly why the console check that consumes this must keep
        rejecting a user whose only groups are empty.
        """
        resolved: set[str] = {str(role_id) for role_id in (role_ids or [])}
        if not group_ids:
            return resolved

        async with self.resource_repository.session() as session:
            group_role_ids = (
                await session.scalars(
                    select(UserGroupRole.role_id).where(
                        UserGroupRole.group_id.in_(group_ids)
                    )
                )
            ).all()
        resolved.update(str(role_id) for role_id in group_role_ids)
        return resolved

    @staticmethod
    async def lock_role(session, role_id: str) -> None:
        """Serialize last-admin checks against each other.

        Any caller that might demote an admin takes this row lock before
        counting, so two concurrent requests cannot each observe an admin the
        other is about to remove and both pass. `group_controller` locks the
        same physical row (by name rather than id), so the group and user paths
        serialize against one another too.

        Only ever locks the `role` row. Deleting a child `user_role` row does
        not take a lock on its parent, so the mutations guarded here cannot
        deadlock against this; inserting one would, and must therefore stay
        inside the same transaction that holds the lock.
        """
        await session.execute(
            select(Role.id).where(Role.id == role_id).with_for_update()
        )

    async def user_ids_with_role(self, role_id: str, session=None) -> set[str]:
        """Ids of live users holding a role directly or through a group.

        Backs the "at least one admin must remain" guard, which needs both the
        count and the identity of the remaining admins, and which would
        otherwise miss admins whose role arrives via group membership and let
        the last one be removed.

        Pass `session` to run inside an existing transaction, so the count and
        the mutation it guards cannot be pulled apart by a concurrent request.
        """
        if session is not None:
            return await self._user_ids_with_role(session, role_id)

        async with self.resource_repository.session() as owned_session:
            return await self._user_ids_with_role(owned_session, role_id)

    @staticmethod
    async def _user_ids_with_role(session, role_id: str) -> set[str]:
        direct = (
            select(UserRole.user_id)
            .join(User, User.id == UserRole.user_id)
            .where(UserRole.role_id == role_id, User.deleted.is_(False))
        )
        via_group = (
            select(UserGroupMember.user_id)
            .join(
                UserGroupRole,
                UserGroupRole.group_id == UserGroupMember.group_id,
            )
            .join(User, User.id == UserGroupMember.user_id)
            .where(UserGroupRole.role_id == role_id, User.deleted.is_(False))
        )
        rows = (await session.scalars(direct.union(via_group))).all()
        return {str(user_id) for user_id in rows}

    async def get_user_resources(
        self,
        user_id: str,
        scope: Optional[ResourceScope] = None,
        scopes: Optional[List[ResourceScope]] = None,
    ) -> List[Resource]:
        """
        Fetch all resources a user has access to, through either a directly
        assigned role or a role granted by one of their groups.

        Args:
            user_id: The ID of the user
            scope: Single scope to filter by (optional)
            scopes: Multiple scopes to filter by (optional)

        Returns:
            List of Resource objects the user has access to
        """
        async with self.resource_repository.session() as session:
            statement = (
                select(Resource)
                .distinct()
                .join(RoleResource, Resource.id == RoleResource.resource_id)
                .where(RoleResource.role_id.in_(self.effective_role_ids(user_id)))
            )

            if scope is not None:
                statement = statement.where(Resource.scope == scope)
            elif scopes is not None:
                statement = statement.where(Resource.scope.in_(scopes))

            result: Result = await session.execute(statement)
            return cast(List[Resource], result.scalars().all())

    def _resource_filters(
        self,
        scope: Optional[ResourceScope] = None,
        scopes: Optional[List[ResourceScope]] = None,
        search: Optional[str] = None,
    ) -> list:
        """Build the WHERE conditions shared by resource listing and counting."""
        conditions: list = []
        if scope is not None:
            conditions.append(Resource.scope == scope)
        elif scopes is not None:
            conditions.append(Resource.scope.in_(scopes))

        if search and search.strip():
            term = f'%{search.strip()}%'
            conditions.append(
                or_(
                    Resource.key.ilike(term),
                    Resource.value.ilike(term),
                    Resource.description.ilike(term),
                )
            )
        return conditions

    async def get_all_resources(
        self,
        scope: Optional[ResourceScope] = None,
        scopes: Optional[List[ResourceScope]] = None,
        search: Optional[str] = None,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> List[Resource]:
        """
        Fetch every resource in the system, optionally filtered by scope/search.

        Used to grant admins implicit access to all resources without requiring
        explicit role assignments, and to power the admin resource listing.

        Args:
            scope: Single scope to filter by (optional)
            scopes: Multiple scopes to filter by (optional)
            search: Case-insensitive term matched against key/value/description
            offset: Number of records to skip (pagination)
            limit: Maximum number of records to return (no limit when None)

        Returns:
            List of all matching Resource objects
        """
        async with self.resource_repository.session() as session:
            statement = select(Resource)
            conditions = self._resource_filters(scope, scopes, search)
            if conditions:
                statement = statement.where(and_(*conditions))

            statement = statement.offset(offset)
            if limit is not None:
                statement = statement.limit(limit)

            result: Result = await session.execute(statement)
            return cast(List[Resource], result.scalars().all())

    async def count_all_resources(
        self,
        scope: Optional[ResourceScope] = None,
        scopes: Optional[List[ResourceScope]] = None,
        search: Optional[str] = None,
    ) -> int:
        """Total number of resources matching the given scope/search filters."""
        async with self.resource_repository.session() as session:
            statement = select(func.count()).select_from(Resource)
            conditions = self._resource_filters(scope, scopes, search)
            if conditions:
                statement = statement.where(and_(*conditions))

            result: Result = await session.execute(statement)
            return result.scalar() or 0

    async def get_user_role_for_scope(
        self, user_id: str, scope: ResourceScope
    ) -> Optional[str]:
        """
        Get the user's role ID for a specific resource scope.
        Admin users are granted access to every scope and their admin role_id is
        returned directly without checking resource assignments.

        Both lookups run over the user's effective roles, so console access (and
        therefore the ability to log in) can come from a group just as well as
        from a direct assignment.

        Args:
            user_id: The ID of the user
            scope: The resource scope to check (usually ResourceScope.CONSOLE)

        Returns:
            The role_id if user has access to the scope, None otherwise
        """
        effective_roles = self.effective_role_ids(user_id)

        async with self.resource_repository.session() as session:
            # Admins have access to all scopes; return their role_id immediately.
            # role_id is not yet known at login, so admin status is resolved by
            # user_id here (the one place this lookup is unavoidable).
            admin_stmt = (
                select(Role.id)
                .where(Role.id.in_(effective_roles))
                .where(Role.name == ADMIN_ROLE_NAME)
            )
            admin_result = await session.execute(admin_stmt)
            admin_role_id = admin_result.scalar()
            if admin_role_id:
                return str(admin_role_id)

            statement = (
                select(Role.id)
                .join(RoleResource, Role.id == RoleResource.role_id)
                .join(Resource, RoleResource.resource_id == Resource.id)
                .where(Role.id.in_(effective_roles))
                .where(Resource.scope == scope)
            )
            result: Result = await session.execute(statement)
            return result.scalar()

    async def invalidate_user_sessions(self, user_id: str) -> None:
        """Drop every live session for a user, cache and DB alike.

        require_auth accepts a session cache hit without checking the DB, and
        cache keys are per session id rather than per user, so deleting the DB
        rows alone would leave cached sessions valid until their TTL. The ids are
        therefore read back from the DB and each cache key removed first.

        The loop stays small because every login path calls this before creating
        its session, so a user normally has a single session row. If a cache
        remove still fails after CacheManager's retries, the exception propagates
        before the DB rows are deleted, so the caller fails rather than reporting
        success with a live session.
        """
        sessions = await self.session_repository.find(user_id=user_id, limit=100)
        for s in sessions:
            self.cache_manager.remove(get_session_cache_key(s.id))
        self.cache_manager.remove(str(user_id))
        await self.session_repository.delete_all(user_id=user_id)

    async def delete_user(self, user_id: str) -> bool:
        await self.user_role_repository.delete_all(user_id=user_id)
        # The user row is only soft-deleted, so the FK cascade never fires and
        # membership rows would otherwise survive and resurrect group-granted
        # access if the account were later reactivated.
        await self.user_group_member_repository.delete_all(user_id=user_id)

        await self.invalidate_user_sessions(user_id)

        response = await self.user_repository.find_one_and_update(
            {'id': user_id}, deleted=True
        )
        return response is not None

    async def reactivate_user(
        self,
        existing_user: User,
        new_user_data: NewUser,
        current_admin_role_id: str,
        response_formatter: ResponseFormatter,
    ) -> JSONResponse:
        # Groups can carry the admin role, so resolve both paths before deciding.
        assignment_role_ids = await self.resolve_assignment_role_ids(
            role_ids=new_user_data.role_id, group_ids=new_user_data.group_ids
        )
        is_reactivating_admin = current_admin_role_id in assignment_role_ids

        try:
            async with self.user_repository.session() as session:
                # Validate roles first
                role_query = select(Role).where(Role.id.in_(new_user_data.role_id))
                role_result = await session.execute(role_query)
                existing_roles = role_result.scalars().all()
                existing_role_ids = {str(role.id) for role in existing_roles}

                invalid_roles = set(new_user_data.role_id) - existing_role_ids
                if invalid_roles:
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content=response_formatter.buildErrorResponse(
                            f'Invalid role IDs: {", ".join(invalid_roles)}'
                        ),
                    )

                # Admins have implicit access to all resources; only validate console
                # resource requirement for non-admin users. Group roles count, but
                # an empty group grants nothing and so cannot satisfy this.
                if not is_reactivating_admin:
                    console_resources_query = (
                        select(Resource)
                        .join(RoleResource, Resource.id == RoleResource.resource_id)
                        .where(
                            and_(
                                RoleResource.role_id.in_(assignment_role_ids),
                                Resource.scope == ResourceScope.CONSOLE,
                            )
                        )
                    )
                    console_result = await session.execute(console_resources_query)
                    console_resources = console_result.scalars().all()
                    if len(console_resources) == 0:
                        return JSONResponse(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            content=response_formatter.buildErrorResponse(
                                'Atleast one console resource is mandatory'
                            ),
                        )

                user_updates: dict[str, Any] = {
                    'deleted': False,
                    'password': hash_password(new_user_data.password),
                    'first_name': new_user_data.first_name,
                    'last_name': new_user_data.last_name,
                    'username': new_user_data.username,
                    'failed_attempts': 0,
                    'locked_until': None,
                    'last_failed_attempt': None,
                    'last_login_at': None,
                }

                updated_user = await self.user_repository.find_one_and_update(
                    {'id': existing_user.id}, **user_updates
                )

                if not updated_user:
                    return JSONResponse(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content=response_formatter.buildErrorResponse(
                            'Failed to update user'
                        ),
                    )

                user_roles = [
                    UserRole(user_id=existing_user.id, role_id=role_id)
                    for role_id in new_user_data.role_id
                ]

                session.add_all(user_roles)
                # delete_user strips membership rows, so reactivation re-adds the
                # groups named in the payload rather than inheriting stale ones.
                session.add_all(
                    [
                        UserGroupMember(user_id=existing_user.id, group_id=group_id)
                        for group_id in new_user_data.group_ids
                    ]
                )
                await session.commit()

                self.cache_manager.invalidate_query(USER_DATA_PATTERN)

                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content=response_formatter.buildSuccessResponse(
                        {
                            'message': 'User account reactivated successfully',
                            'user_id': str(existing_user.id),
                        }
                    ),
                )

        except Exception as e:
            logger.error(f'Failed to reactivate user {existing_user.id}: {str(e)}')
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=response_formatter.buildErrorResponse(
                    f'Failed to reactivate user: {str(e)}'
                ),
            )
