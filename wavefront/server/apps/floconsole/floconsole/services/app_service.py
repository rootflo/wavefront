from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID
from async_lru import alru_cache

from floconsole.db.models.app import App
from floconsole.db.repositories.sql_alchemy_repository import SQLAlchemyRepository


class AppService:
    def __init__(self, app_repository: SQLAlchemyRepository[App]):
        self.app_repository = app_repository

    @alru_cache(maxsize=1, ttl=3600)
    async def get_all_apps(self) -> List[App]:
        """Get all non-deleted apps"""
        return await self.app_repository.find(deleted=False)

    @alru_cache(maxsize=128, ttl=3600)
    async def get_app_by_id(self, app_id: UUID) -> Optional[App]:
        """Get app by ID if not deleted"""
        return await self.app_repository.find_one(id=app_id, deleted=False)

    @alru_cache(maxsize=128, ttl=3600)
    async def get_app_by_name(self, app_name: str) -> Optional[App]:
        """Get app by name if not deleted"""
        return await self.app_repository.find_one(app_name=app_name, deleted=False)

    async def create_app(
        self,
        app_name: str,
        public_url: Optional[str] = None,
        private_url: Optional[str] = None,
        status: str = 'in_progress',
        deployment_type: str = 'manual',
        type: str = 'custom',
        config: dict = {},
    ) -> App:
        """Create a new app"""
        result = await self.app_repository.create(
            app_name=app_name,
            public_url=public_url,
            private_url=private_url,
            status=status,
            deployment_type=deployment_type,
            type=type,
            config=config,
        )
        # Clear all_apps cache since we added a new app
        self._clear_all_apps_cache()
        return result

    async def update_app(self, app_id: UUID, **update_data) -> Optional[App]:
        """Update app by ID"""
        if update_data:
            update_data['updated_at'] = datetime.now(timezone.utc)
            result = await self.app_repository.find_one_and_update(
                filters={'id': app_id, 'deleted': False}, refresh=True, **update_data
            )
            if result:
                # Clear both caches since app was updated
                self._clear_all_caches()
            return result
        return None

    def _clear_all_apps_cache(self):
        """Clear the get_all_apps cache"""
        self.get_all_apps.cache_clear()

    def _clear_all_caches(self):
        """Clear all caches"""
        self._clear_all_apps_cache()
        self.get_app_by_id.cache_clear()

    async def delete_app(self, app_id: UUID) -> Optional[App]:
        """Soft delete app by ID"""
        result = await self.app_repository.find_one_and_update(
            filters={'id': app_id, 'deleted': False},
            deleted=True,
            updated_at=datetime.now(timezone.utc),
        )
        if result:
            # Clear both caches since app was deleted
            self._clear_all_caches()
        return result
