from typing import Dict, Any
from image_search_module.services.algorithm_factory import AlgorithmFactory
from image_search_module.algorithms.base import AlgorithmType


class AlgorithmService:
    """Service for algorithm-specific operations"""

    def __init__(self, algorithm_factory: AlgorithmFactory):
        self.algorithm_factory = algorithm_factory

    def extract_features(
        self, image_bytes: bytes, algorithm_type: str
    ) -> Dict[str, Any]:
        """Extract features using specified algorithm"""
        # Convert string to enum
        algo_enum = AlgorithmType(algorithm_type.lower())

        # Create algorithm instance
        algorithm = self.algorithm_factory.create_algorithm(algo_enum, {})

        # Extract features
        features = algorithm.extract_features(image_bytes)

        # Convert to serializable format
        if hasattr(features, 'to_dict'):
            features_dict = features.to_dict()
        else:
            features_dict = {'features': features}

        return {
            'features': features_dict,
            'algorithm_type': algorithm_type,
            'feature_count': len(features.keypoints)
            if hasattr(features, 'keypoints')
            else 0,
        }
