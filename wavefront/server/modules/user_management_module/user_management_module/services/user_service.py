from typing import List, Optional
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.user import User
from db_repo_module.models.user_role import UserRole
from db_repo_module.models.session import Session
from db_repo_module.models.resource import Resource, ResourceScope
from db_repo_module.models.role import Role
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.cache.cache_manager import CacheManager
from sqlalchemy import select, Result, and_
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
        Fetch all resources accessible to a user based on their roles.

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
                .join(RoleResource, Resource.id == RoleResource.resource_id)
                .join(Role, Role.id == RoleResource.role_id)
                .join(UserRole, UserRole.role_id == Role.id)
                .join(User, UserRole.user_id == User.id)
                .where(UserRole.user_id == user_id)
                .where(User.deleted.is_(False))
            )

            # Apply scope filtering
            if scope is not None:
                statement = statement.where(Resource.scope == scope)
            elif scopes is not None:
                statement = statement.where(Resource.scope.in_(scopes))

            result: Result = await session.execute(statement)
            return result.scalars().all()

    async def get_user_role_for_scope(
        self, user_id: str, scope: ResourceScope
    ) -> Optional[str]:
        """
        Get the user's role ID for a specific resource scope.

        Args:
            user_id: The ID of the user
            scope: The resource scope to check (usually ResourceScope.CONSOLE)

        Returns:
            The role_id if user has access to the scope, None otherwise
        """
        async with self.resource_repository.session() as session:
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

                # Validate console resource requirement
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

                # Handle role assignments
                if (
                    current_admin_role_id in new_user_data.role_id
                ):  # Is creating admin user
                    all_roles = await session.execute(select(Role))
                    all_roles_list = all_roles.scalars().all()
                    user_roles = [
                        UserRole(user_id=existing_user.id, role_id=role.id)
                        for role in all_roles_list
                    ]
                else:  # Is creating user with specific roles
                    user_roles = [
                        UserRole(user_id=existing_user.id, role_id=role_id)
                        for role_id in new_user_data.role_id
                    ]

                session.add_all(user_roles)
                await session.commit()

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
