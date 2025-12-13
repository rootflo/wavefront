from typing import List, Optional
from uuid import UUID

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
            filters={'id': user_id, 'deleted': False}, deleted=True
        )
        return result

    async def count_super_admins(self, super_admin_emails: List[str]) -> int:
        """Count users with super admin emails"""
        users = await self.user_repository.find(email=super_admin_emails, deleted=False)
        return len(users)
