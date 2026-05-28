from typing import List
from uuid import UUID

from floconsole.db.models.app_user import AppUser
from floconsole.db.repositories.sql_alchemy_repository import SQLAlchemyRepository


class AppUserService:
    """Service for managing app-user access relationships"""

    def __init__(self, app_user_repository: SQLAlchemyRepository[AppUser]):
        self.app_user_repository = app_user_repository

    async def grant_app_access(self, user_id: UUID, app_id: UUID) -> AppUser:
        """Grant user access to app"""
        # Use upsert to avoid duplicate key errors
        await self.app_user_repository.upsert(
            filters={'user_id': user_id, 'app_id': app_id}
        )

        # Return the created/existing record
        return await self.app_user_repository.find_one(user_id=user_id, app_id=app_id)

    async def revoke_app_access(self, user_id: UUID, app_id: UUID) -> bool:
        """Revoke user access to app"""
        await self.app_user_repository.delete_all(user_id=user_id, app_id=app_id)
        return True

    async def get_user_apps(self, user_id: UUID) -> List[AppUser]:
        """Get all apps a user has access to"""
        return await self.app_user_repository.find(user_id=user_id)

    async def get_app_users(self, app_id: UUID) -> List[AppUser]:
        """Get all users who have access to an app"""
        return await self.app_user_repository.find(app_id=app_id)
