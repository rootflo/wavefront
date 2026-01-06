from typing import List, Optional
from uuid import UUID

from floconsole.constants.user import UserRole
from floconsole.db.models.user import User
from floconsole.db.repositories.sql_alchemy_repository import SQLAlchemyRepository
from floconsole.utils.password_utils import hash_password


class UserService:
    def __init__(self, user_repository: SQLAlchemyRepository[User]):
        self.user_repository = user_repository

    async def get_all_users(self) -> List[User]:
        """Get all non-deleted users"""
        return await self.user_repository.find(deleted=False)

    async def update_user(self, user_id: UUID, **update_data) -> Optional[User]:
        """Update user by ID"""
        # Hash password if it's being updated
        if 'password' in update_data:
            update_data['password'] = hash_password(update_data['password'])

        if update_data:
            result = await self.user_repository.find_one_and_update(
                filters={'id': user_id, 'deleted': False}, refresh=True, **update_data
            )
            return result
        return None

    async def delete_user(self, user_id: UUID) -> Optional[User]:
        """Soft delete user by ID"""
        result = await self.user_repository.find_one_and_update(
            filters={'id': user_id, 'deleted': False}, refresh=True, deleted=True
        )
        return result

    async def count_owners(self) -> int:
        """Count users with owner role that are not deleted"""
        users = await self.user_repository.find(
            role=UserRole.OWNER.value, deleted=False
        )
        return len(users)

    async def is_owner(self, user_id: UUID) -> bool:
        """Check if user is an owner"""
        user = await self.user_repository.find_one(id=user_id, deleted=False)
        return user is not None and user.role == UserRole.OWNER.value

    async def check_user_has_app_access(self, user_id: UUID, app_id: UUID) -> bool:
        """
        Check if user has access to app.
        Owners have access to all apps.
        App admins need explicit app_user entry.
        """
        user = await self.user_repository.find_one(id=user_id, deleted=False)

        if not user:
            return False

        # Owners have access to all apps
        if user.role == UserRole.OWNER.value:
            return True

        # For app_admins, check app_user junction table
        query = """
            SELECT COUNT(*) as count
            FROM app_user
            WHERE user_id = :user_id AND app_id = :app_id
        """
        result = await self.user_repository.execute_query(
            query, params={'user_id': user_id, 'app_id': app_id}
        )

        return result[0]['count'] > 0 if result else False
