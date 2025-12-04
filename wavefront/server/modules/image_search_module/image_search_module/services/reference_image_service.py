from typing import List, Dict, Any, Optional
import cv2
import numpy as np
from common_module.log.logger import logger

from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.image_search_models import ReferenceImageFeatures
from image_search_module.repositories.sift_features_repository import (
    SIFTFeaturesRepository,
)
from flo_cloud.cloud_storage import CloudStorageManager
from image_search_module.services.algorithm_service import AlgorithmService
from image_search_module.algorithms.sift_matcher import SIFTFeatures


class ReferenceImageService:
    def __init__(
        self,
        features_repository: SQLAlchemyRepository[ReferenceImageFeatures],
        sift_features_repository: SIFTFeaturesRepository,
        algorithm_service: AlgorithmService,
        cloud_storage_manager: CloudStorageManager,
        bucket_name: str,
    ):
        self.cloud_storage_manager = cloud_storage_manager
        self.features_repository = features_repository
        self.sift_features_repository = sift_features_repository
        self.algorithm_service = algorithm_service
        self.cloud_storage_manager = cloud_storage_manager
        self.bucket_name = bucket_name

        logger.info('ReferenceImageService initialized')

    async def add_reference_image(
        self,
        image_bytes: bytes,
        reference_image_id: str,
        algorithm_type: str = 'sift',
        ikb_id: str = None,
        metadata: dict = None,
    ) -> Dict[str, Any]:
        """
        Add a new reference image and extract features for specified algorithms
        """

        self.cloud_storage_manager.save_small_file(
            file_content=image_bytes,
            bucket_name=self.bucket_name,
            key=reference_image_id,
        )

        logger.info(f'Uploaded reference image {reference_image_id} to cloud storage')

        # Extract features for the algorithm
        extraction_results = {}

        features_data = self.algorithm_service.extract_features(
            image_bytes, algorithm_type
        )

        # Store features in database
        await self.features_repository.create(
            reference_image_id=reference_image_id,
            ikb_id=ikb_id,
            algorithm_type=algorithm_type,
            image_url=reference_image_id,
            image_metadata=metadata or {},
        )

        if algorithm_type.lower() == 'sift':
            await self._store_sift_features(reference_image_id, features_data)

        extraction_results[algorithm_type] = {
            'status': 'success',
            'features_count': features_data.get('feature_count', 0),
            'extraction_time_ms': features_data.get('extraction_time_ms', 0),
        }

        logger.info(
            f'Extracted features for {reference_image_id} using {algorithm_type}'
        )

        return {
            'reference_image_id': reference_image_id,
            'algorithm_type': algorithm_type,
            'features_count': features_data.get('feature_count', 0),
            'stored_in': [
                'ReferenceImageFeatures',
                f'{algorithm_type.title()}Features',
            ],
        }

    async def _store_sift_features(self, reference_image_id: str, features_data: dict):
        """Store SIFT features in the dedicated SIFTFeatures table"""
        keypoints = features_data.get('features', {}).get('keypoints', [])
        descriptors = features_data.get('features', {}).get('descriptors', [])

        await self.sift_features_repository.create_sift_features(
            reference_image_id=reference_image_id,
            keypoints=keypoints,
            descriptors=descriptors,
        )

        logger.info(f'Stored {len(keypoints)} SIFT keypoints for {reference_image_id}')

    async def get_reference_features(
        self, algorithm_type: str, ikb_id: str
    ) -> Dict[str, SIFTFeatures]:
        """
        Get all reference features for a specific algorithm type

        Args:
            algorithm_type: Type of algorithm

        Returns:
            Dictionary mapping reference_image_id to SIFTFeatures objects
        """

        if algorithm_type.lower() == 'sift':
            # Get SIFT features from dedicated table
            sift_features = await self.sift_features_repository.get_features_by_ikb(
                ikb_id
            )

            # Group features by reference_image_id and sort by keypoint_id
            grouped_features = {}
            for feature in sift_features:
                ref_id = feature.reference_image_id

                if ref_id not in grouped_features:
                    grouped_features[ref_id] = {
                        'keypoints': [],
                        'descriptors': [],
                        'keypoint_data': [],  # Store (keypoint_id, feature) pairs for sorting
                    }

                # Store keypoint data with ID for proper ordering
                grouped_features[ref_id]['keypoint_data'].append(
                    (
                        feature.keypoint_id,
                        {
                            'pt': [feature.x, feature.y],
                            'size': feature.size,
                            'angle': feature.angle,
                            'response': feature.response,
                            'octave': feature.octave,
                            'class_id': feature.class_id,
                        },
                        feature.descriptor,
                    )
                )

            # Convert to SIFTFeatures objects
            sift_features_dict = {}
            for ref_id, data in grouped_features.items():
                # Sort by keypoint_id to maintain order
                sorted_data = sorted(data['keypoint_data'], key=lambda x: x[0])

                # Extract keypoints and descriptors in correct order
                keypoints = []
                descriptors = []

                for keypoint_id, keypoint_data, descriptor in sorted_data:
                    # Create OpenCV KeyPoint object
                    kp = cv2.KeyPoint(
                        x=keypoint_data['pt'][0],
                        y=keypoint_data['pt'][1],
                        size=keypoint_data['size'],
                        angle=keypoint_data['angle'],
                        response=keypoint_data['response'],
                        octave=keypoint_data['octave'],
                        class_id=keypoint_data['class_id'],
                    )
                    keypoints.append(kp)
                    descriptors.append(descriptor)

                # Convert descriptors to numpy array

                descriptors_array = np.array(descriptors, dtype=np.float32)

                # Create SIFTFeatures object with correct types
                sift_features_dict[ref_id] = SIFTFeatures(
                    keypoints=keypoints,
                    descriptors=descriptors_array,
                    image_shape=(800, 600),  # Default shape
                )

            logger.info(
                f'Retrieved {len(sift_features_dict)} reference features for {algorithm_type}'
            )
            return sift_features_dict

        else:
            # Handle other algorithm types
            logger.warning(f'Algorithm type {algorithm_type} not implemented yet')
            return {}

    async def delete_reference_image(
        self, reference_image_id: str, algorithm_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Delete a reference image and its features

        Args:
            reference_image_id: ID of the reference image
            algorithm_types: Optional list of algorithm types to delete features for

        Returns:
            Dictionary with deletion results
        """
        # Delete from cloud storage
        await self.cloud_storage_manager.delete_file(
            bucket_name=self.bucket_name, file_path=reference_image_id
        )

        # Delete features from database
        deleted_features = await self.features_repository.delete_by_reference_id(
            reference_image_id,
            algorithm_types[0]
            if algorithm_types and len(algorithm_types) == 1
            else None,
        )

        result = {
            'reference_image_id': reference_image_id,
            'deleted_features_count': deleted_features,
            'deleted_from_storage': True,
        }

        logger.info(f'Successfully deleted reference image {reference_image_id}')
        return result

    async def ensure_features_available(self, algorithm_type: str) -> bool:
        features = await self.get_reference_features(algorithm_type)
        is_available = len(features) > 0

        if not is_available:
            logger.warning(f'No reference features available for {algorithm_type}')
        else:
            logger.info(
                f'Features available for {algorithm_type}: {len(features)} references'
            )

        return is_available
