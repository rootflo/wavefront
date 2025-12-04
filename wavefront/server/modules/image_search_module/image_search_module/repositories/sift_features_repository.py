from typing import List
from db_repo_module.models.image_search_models import ReferenceImageFeatures
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.image_search_models import SIFTFeatures
from sqlalchemy import select


class SIFTFeaturesRepository(SQLAlchemyRepository[SIFTFeatures]):
    """Repository for SIFT features"""

    async def create_sift_features(
        self,
        reference_image_id: str,
        keypoints: List[dict],
        descriptors: List[List[float]],
    ) -> List[SIFTFeatures]:
        """Create SIFT features for a reference image"""
        sift_features = []

        for i, (keypoint, descriptor) in enumerate(zip(keypoints, descriptors)):
            # Create the feature using the parent's create method with keyword arguments
            feature = await self.create(
                reference_image_id=reference_image_id,
                keypoint_id=i,  # Ensure sequential ordering
                x=keypoint['pt'][0],
                y=keypoint['pt'][1],
                size=keypoint['size'],
                angle=keypoint['angle'],
                response=keypoint['response'],
                octave=keypoint['octave'],
                class_id=keypoint['class_id'],
                descriptor=descriptor,
            )
            sift_features.append(feature)

        return sift_features

    async def get_features_by_ikb(self, ikb_id: str) -> List[SIFTFeatures]:
        """Get SIFT features only from specific IKB"""
        async with self.session() as session:
            stmt = (
                select(SIFTFeatures)
                .join(
                    ReferenceImageFeatures,
                    SIFTFeatures.reference_image_id
                    == ReferenceImageFeatures.reference_image_id,
                )
                .where(ReferenceImageFeatures.ikb_id == ikb_id)
            )

            result = await session.execute(stmt)
            return result.scalars().all()
