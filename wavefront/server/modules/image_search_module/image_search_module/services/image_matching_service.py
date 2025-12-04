from typing import List, Dict, Any, Optional
from common_module.log.logger import logger

from image_search_module.algorithms.base import (
    ImageMatchingAlgorithm,
    MatchResult,
    AlgorithmType,
)
from image_search_module.services.algorithm_factory import AlgorithmFactory
from image_search_module.services.reference_image_service import ReferenceImageService


class ImageMatchingService:
    """Main service for image matching operations"""

    def __init__(
        self,
        algorithm_factory: AlgorithmFactory,
        reference_service: ReferenceImageService,
        active_algorithm_type: AlgorithmType,
        algorithm_config: Dict[str, Any],
        max_results: int = 10,
    ):
        self.algorithm_factory = algorithm_factory
        self.reference_service = reference_service
        self.active_algorithm_type = active_algorithm_type
        self.algorithm_config = algorithm_config
        self.max_results = max_results

        # Initialize active algorithm
        self.active_algorithm = self._create_active_algorithm()

    def _create_active_algorithm(self) -> ImageMatchingAlgorithm:
        """Create the currently active algorithm instance"""
        algo_config = self.algorithm_config.get(self.active_algorithm_type.value, {})
        return self.algorithm_factory.create_algorithm(
            self.active_algorithm_type, algo_config
        )

    async def match_image(
        self,
        image_bytes: bytes,
        ikb_id: str,
        threshold: Optional[float] = None,
        max_results: Optional[int] = None,
        algorithm_type: Optional[AlgorithmType] = None,
    ) -> List[MatchResult]:
        """
        Main image matching method
        """

        # Use provided values or defaults
        max_results = max_results or self.max_results
        algorithm = (
            self.active_algorithm
            if algorithm_type is None
            else self.algorithm_factory.create_algorithm(
                algorithm_type, self.algorithm_config.get(algorithm_type.value, {})
            )
        )

        logger.info(f'Starting image matching with {algorithm.__class__.__name__}')

        # Extract features from query image
        query_features = algorithm.extract_features(image_bytes)
        logger.info('Query features extracted successfully')

        # Get reference features for this algorithm
        algorithm_type_str = (
            algorithm_type.value if algorithm_type else self.active_algorithm_type.value
        )
        reference_features = await self.reference_service.get_reference_features(
            algorithm_type=algorithm_type_str, ikb_id=ikb_id
        )
        logger.info(f'Retrieved {len(reference_features)} reference features')

        # Perform batch matching
        all_matches = algorithm.batch_match(query_features, reference_features)
        logger.info(f'Completed matching, found {len(all_matches)} comparisons')

        # Filter by threshold and sort
        valid_matches = [match for match in all_matches if match.is_match]

        sorted_matches = sorted(
            valid_matches, key=lambda x: x.match_score, reverse=True
        )[:max_results]

        logger.info(
            f'Returning {len(sorted_matches)} matches above threshold {threshold}'
        )

        return sorted_matches

    def get_algorithm_info(
        self, algorithm_type: Optional[AlgorithmType] = None
    ) -> Dict[str, Any]:
        """Get information about an algorithm"""

        algo_type = algorithm_type or self.active_algorithm_type
        algorithm = self.algorithm_factory.create_algorithm(
            algo_type, self.algorithm_config.get(algo_type.value, {})
        )

        return algorithm.get_algorithm_info().to_dict()
