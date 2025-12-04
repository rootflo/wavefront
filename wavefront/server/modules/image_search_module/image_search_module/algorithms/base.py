from abc import ABC, abstractmethod
from typing import Dict, List, Any
from dataclasses import dataclass
from enum import Enum


class AlgorithmType(Enum):
    """Supported matching algorithms"""

    SIFT = 'sift'
    # SAM_DINOV2 = "sam_dinov2"


@dataclass
class MatchResult:
    """Standardized match result across all algorithms"""

    algorithm_type: str
    reference_id: str
    match_score: float
    is_match: bool
    confidence: float
    processing_time_ms: float
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'algorithm_type': self.algorithm_type,
            'reference_id': self.reference_id,
            'match_score': self.match_score,
            'is_match': self.is_match,
            'confidence': self.confidence,
            'processing_time_ms': self.processing_time_ms,
            'metadata': self.metadata,
        }


@dataclass
class AlgorithmInfo:
    """Algorithm metadata and capabilities"""

    name: str
    version: str
    description: str
    supported_formats: List[str]
    performance_characteristics: Dict[str, Any]
    requirements: Dict[str, Any]


class ImageMatchingAlgorithm(ABC):
    """Abstract base class for all image matching algorithms"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.algorithm_type = self.__class__.__name__.lower().replace('matcher', '')

    @abstractmethod
    def extract_features(self, image_bytes: bytes) -> Any:
        """
        Extract features from image bytes

        Args:
            image_bytes: Raw image data

        Returns:
            Algorithm-specific feature representation
        """
        pass

    @abstractmethod
    def match_against_reference(
        self, query_features: Any, reference_features: Any, reference_id: str
    ) -> MatchResult:
        """
        Match query features against single reference

        Args:
            query_features: Features extracted from query image
            reference_features: Features from reference image
            reference_id: Unique identifier for reference

        Returns:
            MatchResult with similarity score and metadata
        """
        pass

    @abstractmethod
    def batch_match(
        self, query_features: Any, reference_features_map: Dict[str, Any]
    ) -> List[MatchResult]:
        """
        Efficiently match query against multiple references

        Args:
            query_features: Features from query image
            reference_features_map: Dict of {reference_id: features}

        Returns:
            List of MatchResult objects
        """
        pass

    @abstractmethod
    def get_algorithm_info(self) -> AlgorithmInfo:
        """Return algorithm metadata and capabilities"""
        pass

    def preprocess_image(self, image_bytes: bytes, target_width: int = 800) -> Any:
        """Common image preprocessing logic"""
        # This would contain shared preprocessing logic
        pass
