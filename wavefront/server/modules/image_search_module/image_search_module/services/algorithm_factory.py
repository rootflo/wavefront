from typing import Dict, Any
from image_search_module.algorithms.base import ImageMatchingAlgorithm, AlgorithmType
from image_search_module.algorithms.sift_matcher import SIFTMatcher


class AlgorithmFactory:
    """Factory for creating algorithm instances"""

    def __init__(self):
        self._algorithms = {
            AlgorithmType.SIFT: SIFTMatcher,
            # Add other algorithms here as you implement them
        }

    def create_algorithm(
        self, algorithm_type: AlgorithmType, config: Dict[str, Any]
    ) -> ImageMatchingAlgorithm:
        """
        Create an algorithm instance

        Args:
            algorithm_type: Type of algorithm to create
            config: Configuration for the algorithm

        Returns:
            Algorithm instance
        """
        if algorithm_type not in self._algorithms:
            raise ValueError(f'Unsupported algorithm type: {algorithm_type}')

        algorithm_class = self._algorithms[algorithm_type]
        return algorithm_class(config)

    def get_supported_algorithms(self) -> list:
        """Get list of supported algorithm types"""
        return list(self._algorithms.keys())
