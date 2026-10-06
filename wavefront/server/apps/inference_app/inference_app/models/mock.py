"""Whether the inference app serves mock embeddings (see service/mock_embeddings.py)."""

import importlib.util


def torch_available() -> bool:
    return importlib.util.find_spec('torch') is not None


def use_mock_models(setting: str = 'auto') -> bool:
    """mock_models: 'true' / 'false', or 'auto' (the default) for
    mock mode exactly when torch isn't installed (Intel Macs)."""
    normalized = setting.strip().lower()
    if normalized in ('true', '1', 'yes'):
        return True
    if normalized in ('false', '0', 'no'):
        return False
    return not torch_available()
