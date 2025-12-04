import cv2
import numpy as np
import time
from typing import Dict, List, Any
from dataclasses import dataclass

from image_search_module.algorithms.base import (
    ImageMatchingAlgorithm,
    MatchResult,
    AlgorithmInfo,
)


@dataclass
class SIFTFeatures:
    """SIFT-specific feature representation"""

    keypoints: List[cv2.KeyPoint]
    descriptors: np.ndarray
    image_shape: tuple

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for storage"""
        return {
            'keypoints': [
                {
                    'pt': kp.pt,
                    'size': kp.size,
                    'angle': kp.angle,
                    'response': kp.response,
                    'octave': kp.octave,
                    'class_id': kp.class_id,
                }
                for kp in self.keypoints
            ],
            'descriptors': self.descriptors.tolist()
            if self.descriptors is not None
            else None,
            'image_shape': self.image_shape,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SIFTFeatures':
        """Deserialize from storage"""
        keypoints = []
        for kp_data in data['keypoints']:
            kp = cv2.KeyPoint(
                x=kp_data['pt'][0],
                y=kp_data['pt'][1],
                size=kp_data['size'],
                angle=kp_data['angle'],
                response=kp_data['response'],
                octave=kp_data['octave'],
                class_id=kp_data['class_id'],
            )
            keypoints.append(kp)

        descriptors = (
            np.array(data['descriptors'], dtype=np.float32)
            if data['descriptors']
            else None
        )
        return cls(
            keypoints=keypoints,
            descriptors=descriptors,
            image_shape=data['image_shape'],
        )


class SIFTMatcher(ImageMatchingAlgorithm):
    """SIFT-based image matching implementation"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.max_features = config.get('max_features', 5000)
        self.lowe_ratio = config.get('lowe_ratio', 0.75)
        self.match_threshold = config.get('match_threshold', 10)
        self.min_homography_matches = config.get('min_homography_matches', 4)
        self.target_width = config.get('target_width', 800)

        self.sift = cv2.SIFT_create(nfeatures=self.max_features)

    def extract_features(self, image_bytes: bytes) -> SIFTFeatures:
        """Extract SIFT features from image"""
        try:
            # Convert bytes to image
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)

            if image is None:
                raise ValueError('Could not decode image')

            # Preprocess image
            processed_image = self._preprocess_image(image)

            # Extract SIFT features
            keypoints, descriptors = self.sift.detectAndCompute(processed_image, None)

            return SIFTFeatures(
                keypoints=keypoints,
                descriptors=descriptors,
                image_shape=processed_image.shape,
            )

        except Exception as e:
            raise RuntimeError(f'SIFT feature extraction failed: {e}')

    def match_against_reference(
        self,
        query_features: SIFTFeatures,
        reference_features: SIFTFeatures,
        reference_id: str,
    ) -> MatchResult:
        """Match SIFT features against single reference"""

        start_time = time.perf_counter()

        try:
            # Perform feature matching
            matches = self._match_features(
                query_features.descriptors, reference_features.descriptors
            )

            # Verify with homography if enough matches
            inlier_matches, homography, is_valid = self._verify_homography(
                query_features.keypoints, reference_features.keypoints, matches
            )

            match_score = len(inlier_matches)
            is_match = match_score >= self.match_threshold and is_valid
            confidence = min(match_score / (self.match_threshold * 2), 1.0)

            end_time = time.perf_counter()
            processing_time_ms = (end_time - start_time) * 1000

            return MatchResult(
                algorithm_type=self.algorithm_type,
                reference_id=reference_id,
                match_score=match_score,
                is_match=is_match,
                confidence=confidence,
                processing_time_ms=processing_time_ms,
                metadata={
                    'total_matches': len(matches),
                    'inlier_matches': len(inlier_matches),
                    'homography_valid': is_valid,
                    'lowe_ratio': self.lowe_ratio,
                },
            )

        except Exception as e:
            return MatchResult(
                algorithm_type=self.algorithm_type,
                reference_id=reference_id,
                match_score=0.0,
                is_match=False,
                confidence=0.0,
                processing_time_ms=0.0,
                metadata={'error': str(e)},
            )

    def batch_match(
        self,
        query_features: SIFTFeatures,
        reference_features_map: Dict[str, SIFTFeatures],
    ) -> List[MatchResult]:
        """Batch match against multiple references"""

        results = []
        for ref_id, ref_features in reference_features_map.items():
            result = self.match_against_reference(query_features, ref_features, ref_id)
            results.append(result)

        return results

    def get_algorithm_info(self) -> AlgorithmInfo:
        """Return SIFT algorithm information"""
        return AlgorithmInfo(
            name='SIFT',
            version='1.0.0',
            description='Scale-Invariant Feature Transform for feature-based matching',
            supported_formats=['jpg', 'jpeg', 'png', 'bmp', 'tiff'],
            performance_characteristics={
                'rotation_invariant': True,
                'scale_invariant': True,
                'illumination_robust': True,
                'typical_processing_time_ms': '100-500',
                'memory_usage': 'moderate',
            },
            requirements={
                'opencv': '>=4.8.0',
                'min_image_size': '100x100',
                'recommended_image_size': '800x600',
            },
        )

    def _preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """Preprocess image for SIFT"""
        # Resize if too large
        if image.shape[1] > self.target_width:
            scale = self.target_width / image.shape[1]
            new_height = int(image.shape[0] * scale)
            image = cv2.resize(
                image, (self.target_width, new_height), interpolation=cv2.INTER_AREA
            )

        # Apply CLAHE for contrast enhancement
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        image = clahe.apply(image)

        # Apply slight Gaussian blur
        image = cv2.GaussianBlur(image, (3, 3), 0.5)

        return image

    def _match_features(self, desc1: np.ndarray, desc2: np.ndarray) -> List[cv2.DMatch]:
        """Match SIFT descriptors using Lowe's ratio test"""
        if desc1 is None or desc2 is None or len(desc1) < 2 or len(desc2) < 2:
            return []

        try:
            bf = cv2.BFMatcher()
            matches = bf.knnMatch(desc1, desc2, k=2)

            # Apply Lowe's ratio test
            good_matches = []
            for match_pair in matches:
                if len(match_pair) == 2:
                    m, n = match_pair
                    if m.distance < self.lowe_ratio * n.distance:
                        good_matches.append(m)

            return good_matches

        except Exception:
            return []

    def _verify_homography(
        self,
        kp1: List[cv2.KeyPoint],
        kp2: List[cv2.KeyPoint],
        matches: List[cv2.DMatch],
    ) -> tuple:
        """Verify matches using homography estimation"""
        if len(matches) < self.min_homography_matches:
            return matches, None, False

        try:
            # Extract matched points
            src_pts = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(
                -1, 1, 2
            )
            dst_pts = np.float32([kp2[m.trainIdx].pt for m in matches]).reshape(
                -1, 1, 2
            )

            # Find homography
            homography, mask = cv2.findHomography(
                src_pts, dst_pts, cv2.RANSAC, 5.0, maxIters=5000, confidence=0.995
            )

            if homography is not None:
                # Filter inlier matches
                inlier_matches = [matches[i] for i in range(len(matches)) if mask[i]]

                # Check homography quality
                det = np.linalg.det(homography[:2, :2])
                is_valid = (
                    0.1 < abs(det) < 10
                    and len(inlier_matches) >= self.min_homography_matches
                )

                return inlier_matches, homography, is_valid

            return matches, None, False

        except Exception:
            return matches, None, False
