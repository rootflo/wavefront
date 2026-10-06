"""Whether the inference app serves mock embeddings (see service/mock_embeddings.py)."""

import importlib.util

from inference_app.env import INFERENCE_MOCK_MODELS


def torch_available() -> bool:
    return importlib.util.find_spec('torch') is not None


def use_mock_models(setting: str = INFERENCE_MOCK_MODELS) -> bool:
    """INFERENCE_MOCK_MODELS: 'true' / 'false', or 'auto' (the default) for
    mock mode exactly when torch isn't installed (Intel Macs)."""
    if setting in ('true', '1', 'yes'):
        return True
    if setting in ('false', '0', 'no'):
        return False
    return not torch_available()
