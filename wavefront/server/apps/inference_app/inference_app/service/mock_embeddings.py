"""Stand-in embedding models for machines that can't run the real ones.

PyTorch has no build at the supported version (>= 2.6) for Intel Macs, so
there the inference app serves these instead (see inference_app.mock). They
return what the real models return -- same shapes, same formats, same errors
for undecodable images -- but the vectors are synthetic, for integration
testing only:

- Images: a fixed pseudo-random unit vector per decoded image, so the same
  picture (even re-encoded) always maps to the same vector and searching with
  an uploaded image finds it again.
- Text: hashed bag-of-words vectors with a shared baseline, so unrelated
  texts score about 0.5 (like real BGE-M3) and texts that share words score
  higher; sparse vectors weight the words two texts share.

No torch, transformers or model files are needed.
"""

import hashlib
import io
import math
import re
from collections import Counter
from typing import Any, Dict, List

import numpy as np
from PIL import Image

from common_module.utils.image_formats import SUPPORTED_PILLOW_FORMATS

CLIP_DIM = 512
DINO_DIM = 1024
TEXT_DENSE_DIM = 1024
TEXT_SPARSE_DIM = 250002
# Token ids 0-3 are BGE-M3's special tokens (<s>, <pad>, </s>, <unk>)
_FIRST_WORD_TOKEN_ID = 4
_MAX_TOKENS = 512


def _stable_hash(*parts: bytes) -> int:
    digest = hashlib.sha256(b'\x00'.join(parts)).digest()
    return int.from_bytes(digest[:8], 'big')


def _unit_vector(seed: int, dim: int) -> List[float]:
    vector = np.random.default_rng(seed).standard_normal(dim)
    return (vector / np.linalg.norm(vector)).tolist()


def _decode(image_content: bytes) -> Image.Image:
    return Image.open(
        io.BytesIO(image_content), formats=SUPPORTED_PILLOW_FORMATS
    ).convert('RGB')


class MockImageEmbedding:
    """Same interface as ImageEmbedding (CLIP 512 + DINOv3 1024)."""

    def _vectors(self, image: Image.Image) -> Dict[str, List[float]]:
        pixels = image.tobytes() + repr(image.size).encode()
        return {
            'clip': _unit_vector(_stable_hash(b'clip', pixels), CLIP_DIM),
            'dino': _unit_vector(_stable_hash(b'dino', pixels), DINO_DIM),
        }

    def query_embed(self, image_content: bytes) -> List[Dict[str, List[float]]]:
        try:
            image = _decode(image_content)
        except Exception as e:
            raise ValueError(f'Failed to decode image: {e}') from e
        vectors = self._vectors(image)
        return [{'clip': vectors['clip']}, {'dino': vectors['dino']}]

    def query_embed_batch(
        self, image_batch: List[bytes]
    ) -> List[Dict[str, List[List[float]]]]:
        if not image_batch:
            return []
        vectors = []
        for idx, image_content in enumerate(image_batch):
            try:
                vectors.append(self._vectors(_decode(image_content)))
            except Exception as e:
                raise ValueError(f'Failed to decode image at index {idx}: {e}') from e
        return [
            {'clip': [v['clip'] for v in vectors]},
            {'dino': [v['dino'] for v in vectors]},
        ]


class MockTextEmbedding:
    """Same interface as TextEmbedding (BGE-M3 dense + sparse)."""

    dense_dim = TEXT_DENSE_DIM
    sparse_dim = TEXT_SPARSE_DIM

    @staticmethod
    def _words(text: str) -> List[str]:
        return re.findall(r'\w+', text.lower())[:_MAX_TOKENS]

    @staticmethod
    def _token_id(word: str) -> int:
        span = TEXT_SPARSE_DIM - _FIRST_WORD_TOKEN_ID
        return _FIRST_WORD_TOKEN_ID + _stable_hash(b'tok', word.encode()) % span

    def _dense(self, words: List[str]) -> List[float]:
        """Hashed bag-of-words in dims 1.., plus an equal-weight component in
        dim 0 that every text shares. Cosine similarity is then
        (word-overlap cosine + 1) / 2: about 0.5 for unrelated text and higher
        the more words two texts share -- the high baseline real BGE-M3 dense
        vectors have, so default retrieval thresholds behave similarly."""
        words_part = np.zeros(TEXT_DENSE_DIM)
        for word in words:
            h = _stable_hash(b'dense', word.encode())
            words_part[1 + h % (TEXT_DENSE_DIM - 1)] += 1.0 if (h >> 32) & 1 else -1.0
        norm = np.linalg.norm(words_part)
        if norm:
            words_part /= norm
        words_part[0] = 1.0
        return (words_part / np.linalg.norm(words_part)).tolist()

    def _sparse(self, words: List[str]) -> Dict[str, List]:
        counts = Counter(self._token_id(word) for word in words)
        weights = {
            token_id: round(0.1 + 0.2 * math.log1p(count), 4)
            for token_id, count in counts.items()
        }
        indices = sorted(weights)
        return {'indices': indices, 'values': [weights[i] for i in indices]}

    def embed(
        self,
        texts: List[str],
        return_dense: bool = True,
        return_sparse: bool = True,
    ) -> List[Dict[str, Any]]:
        results = []
        for text in texts:
            words = self._words(text)
            result: Dict[str, Any] = {}
            if return_dense:
                result['dense'] = self._dense(words)
            if return_sparse:
                result['sparse'] = self._sparse(words)
            results.append(result)
        return results
