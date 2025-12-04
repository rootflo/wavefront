from typing import List, Optional
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.ikb_models import ImageKnowledgeBase
from image_search_module.models.ikb_models import IKBInfo, IKBType, IKBStatus
from image_search_module.algorithms.base import AlgorithmType


class IKBRepository:
    """Repository for Image Knowledge Base operations"""

    def __init__(self, db_repository: SQLAlchemyRepository[ImageKnowledgeBase]):
        self.db_repository = db_repository

    async def create_ikb(self, ikb_info: IKBInfo) -> ImageKnowledgeBase:
        """Create a new IKB in the database"""
        return await self.db_repository.create(
            ikb_id=ikb_info.ikb_id,
            name=ikb_info.name,
            description=ikb_info.description,
            ikb_type=ikb_info.ikb_type.value,
            algorithm_type=ikb_info.algorithm_type.value,
            status=ikb_info.status.value,
            config=ikb_info.config,
            image_count=ikb_info.image_count,
        )

    async def get_ikb(self, ikb_id: str) -> Optional[ImageKnowledgeBase]:
        """Get IKB by ID"""
        return await self.db_repository.find_one(ikb_id=ikb_id)

    async def list_ikbs(
        self, ikb_type: Optional[IKBType] = None
    ) -> List[ImageKnowledgeBase]:
        """List all IKBs, optionally filtered by type"""
        filters = {}
        if ikb_type:
            filters['ikb_type'] = ikb_type.value

        return await self.db_repository.find(**filters)

    async def update_ikb(self, ikb_id: str, **updates) -> Optional[ImageKnowledgeBase]:
        """Update IKB"""
        # Use find_one_and_update method
        filters = {'ikb_id': ikb_id}
        return await self.db_repository.find_one_and_update(filters, **updates)

    async def delete_ikb(self, ikb_id: str) -> bool:
        """Delete IKB"""
        # Use delete_all method with filter
        await self.db_repository.delete_all(ikb_id=ikb_id)
        return True

    async def increment_image_count(self, ikb_id: str) -> bool:
        """Increment the image count for an IKB"""
        # Get current IKB
        ikb = await self.get_ikb(ikb_id)
        if ikb:
            # Update with incremented count
            await self.update_ikb(ikb_id, image_count=ikb.image_count + 1)
            return True
        return False

    def _convert_to_ikb_info(self, ikb_db: ImageKnowledgeBase) -> IKBInfo:
        """Convert database model to IKBInfo"""
        return IKBInfo(
            ikb_id=ikb_db.ikb_id,
            name=ikb_db.name,
            description=ikb_db.description,
            ikb_type=IKBType(ikb_db.ikb_type),
            algorithm_type=AlgorithmType(ikb_db.algorithm_type),
            status=IKBStatus(ikb_db.status),
            image_count=ikb_db.image_count,
            created_at=ikb_db.created_at,
            updated_at=ikb_db.updated_at,
            config=ikb_db.config,
        )
