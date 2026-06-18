from typing import List, Optional
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.user import User
from db_repo_module.models.user_role import UserRole
from db_repo_module.models.session import Session
from db_repo_module.models.resource import Resource, ResourceScope
from db_repo_module.models.role import Role
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.cache.cache_manager import CacheManager
from sqlalchemy import select, Result, and_, or_, func
from user_management_module.constants.auth import ADMIN_ROLE_NAME
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
    ):
        self.user_repository = user_repository
        self.user_role_repository = user_role_repository
        self.session_repository = session_repository
        self.resource_repository = resource_repository
        self.cache_manager = cache_manager

    async def get_user_resources(
        self,
        user_id: str,
        scope: Optional[ResourceScope] = None,
        scopes: Optional[List[ResourceScope]] = None,
    ) -> List[Resource]:
        """
        Fetch all resources a user has access to through their role assignments.

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
                .join(Role, Role.id == RoleResource.role_id)
                .join(UserRole, UserRole.role_id == Role.id)
                .join(User, UserRole.user_id == User.id)
                .where(UserRole.user_id == user_id)
                .where(User.deleted.is_(False))
            )

            if scope is not None:
                statement = statement.where(Resource.scope == scope)
            elif scopes is not None:
                statement = statement.where(Resource.scope.in_(scopes))

            result: Result = await session.execute(statement)
            return result.scalars().all()

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
            return result.scalars().all()

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

        Args:
            user_id: The ID of the user
            scope: The resource scope to check (usually ResourceScope.CONSOLE)

        Returns:
            The role_id if user has access to the scope, None otherwise
        """
        async with self.resource_repository.session() as session:
            # Admins have access to all scopes; return their role_id immediately.
            # role_id is not yet known at login, so admin status is resolved by
            # user_id here (the one place this lookup is unavoidable).
            admin_stmt = (
                select(UserRole.role_id)
                .join(Role, UserRole.role_id == Role.id)
                .join(User, UserRole.user_id == User.id)
                .where(UserRole.user_id == user_id)
                .where(User.deleted.is_(False))
                .where(Role.name == ADMIN_ROLE_NAME)
            )
            admin_result = await session.execute(admin_stmt)
            admin_role_id = admin_result.scalar()
            if admin_role_id:
                return str(admin_role_id)

            statement = (
                select(UserRole.role_id)
                .join(Role, UserRole.role_id == Role.id)
                .join(RoleResource, Role.id == RoleResource.role_id)
                .join(Resource, RoleResource.resource_id == Resource.id)
                .join(User, UserRole.user_id == User.id)
                .where(UserRole.user_id == user_id)
                .where(User.deleted.is_(False))
                .where(Resource.scope == scope)
            )
            result: Result = await session.execute(statement)
            return result.scalar()

    async def delete_user(self, user_id: str) -> bool:
        await self.user_role_repository.delete_all(user_id=user_id)

        sessions = await self.session_repository.find(user_id=user_id, limit=1000)
        for s in sessions:
            self.cache_manager.remove(f'session_{s.id}')

        self.cache_manager.remove(user_id)

        await self.session_repository.delete_all(user_id=user_id)

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
        is_reactivating_admin = current_admin_role_id in new_user_data.role_id

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
                # resource requirement for non-admin users
                if not is_reactivating_admin:
                    console_resources_query = (
                        select(Resource)
                        .join(RoleResource, Resource.id == RoleResource.resource_id)
                        .where(
                            and_(
                                RoleResource.role_id.in_(new_user_data.role_id),
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

                user_updates = {
                    'deleted': False,
                    'password': hash_password(new_user_data.password),
                    'first_name': new_user_data.first_name,
                    'last_name': new_user_data.last_name,
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
                await session.commit()

                self.cache_manager.invalidate_query('user_data_*')

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
