"""
Tests that the embedding models load without trust_remote_code, so Python
files in a synced model directory are never executed.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip('torch')

from transformers import AutoModel, DINOv3ViTConfig, DINOv3ViTModel  # noqa: E402

from inference_app.service import image_embedding  # noqa: E402
from inference_app.service.image_embedding import ImageEmbedding  # noqa: E402

LOADERS = ('CLIPProcessor', 'CLIPModel', 'AutoImageProcessor', 'AutoModel')


def test_no_model_or_processor_is_loaded_with_trust_remote_code():
    mocks = {name: MagicMock() for name in LOADERS}
    with patch.multiple(image_embedding, **mocks):
        ImageEmbedding(clip_model_dir='/models/clip', dino_model_dir='/models/dino')

    for name, mock in mocks.items():
        mock.from_pretrained.assert_called_once()
        kwargs = mock.from_pretrained.call_args.kwargs
        assert not kwargs.get('trust_remote_code'), f'{name} loaded with remote code'


def save_tiny_dinov3(path):
    config = DINOv3ViTConfig(
        hidden_size=32,
        intermediate_size=64,
        num_hidden_layers=1,
        num_attention_heads=2,
        image_size=32,
        patch_size=16,
    )
    DINOv3ViTModel(config).save_pretrained(path)


def test_dinov3_loads_with_builtin_class(tmp_path):
    save_tiny_dinov3(tmp_path)

    model = AutoModel.from_pretrained(tmp_path)

    assert isinstance(model, DINOv3ViTModel)


def test_custom_code_in_model_directory_is_not_executed(tmp_path):
    """A model directory whose config points auto_map at its own Python file
    (what an attacker with bucket write access could add) loads the built-in
    class and never imports that file."""
    save_tiny_dinov3(tmp_path)
    marker = tmp_path / 'custom_code_ran'
    (tmp_path / 'evil.py').write_text(
        f'open({str(marker)!r}, "w").write("ran")\n'
        'from transformers import DINOv3ViTModel as EvilModel\n'
    )
    config_path = tmp_path / 'config.json'
    config = json.loads(config_path.read_text())
    config['auto_map'] = {'AutoModel': 'evil.EvilModel'}
    config_path.write_text(json.dumps(config))

    model = AutoModel.from_pretrained(tmp_path)

    assert isinstance(model, DINOv3ViTModel)
    assert not marker.exists(), 'model directory code was executed'
