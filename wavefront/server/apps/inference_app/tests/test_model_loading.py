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


def save_tiny_clip_like_the_repo(path):
    """What openai/clip-vit-base-patch32 ships: pytorch_model.bin, plus TF and
    Flax weights we don't use."""
    from transformers import CLIPConfig, CLIPModel

    config = CLIPConfig(
        text_config={
            'hidden_size': 32,
            'intermediate_size': 37,
            'num_hidden_layers': 1,
            'num_attention_heads': 2,
            'vocab_size': 99,
        },
        vision_config={
            'hidden_size': 32,
            'intermediate_size': 37,
            'num_hidden_layers': 1,
            'num_attention_heads': 2,
            'image_size': 32,
            'patch_size': 16,
        },
        projection_dim=16,
    )
    CLIPModel(config).save_pretrained(path, safe_serialization=False)
    (path / 'tf_model.h5').write_bytes(b'tf weights')
    (path / 'flax_model.msgpack').write_bytes(b'flax weights')


def test_clip_is_converted_to_safetensors_and_loads(tmp_path):
    from transformers import CLIPModel

    from inference_app.scripts.download_models import (
        MODELS,
        convert_clip_to_safetensors,
    )

    save_tiny_clip_like_the_repo(tmp_path)

    convert_clip_to_safetensors(tmp_path)

    assert (tmp_path / 'model.safetensors').is_file()
    for removed in ('pytorch_model.bin', 'tf_model.h5', 'flax_model.msgpack'):
        assert not (tmp_path / removed).exists()
    # Loads from safetensors only, so it works even where transformers
    # refuses .bin files (torch < 2.6, e.g. the Intel Mac build).
    model = CLIPModel.from_pretrained(tmp_path, use_safetensors=True)
    assert isinstance(model, CLIPModel)

    [entry] = [m for m in MODELS if m['repo_id'] == 'openai/clip-vit-base-patch32']
    assert entry['post_process'] == 'convert_clip_to_safetensors'
    assert not any(
        name in entry['allow_patterns']
        for name in ('tf_model.h5', 'flax_model.msgpack')
    )


def test_clip_conversion_keeps_the_weights(tmp_path):
    import torch
    from safetensors.torch import load_file

    from inference_app.scripts.download_models import convert_clip_to_safetensors

    save_tiny_clip_like_the_repo(tmp_path)
    before = torch.load(tmp_path / 'pytorch_model.bin', weights_only=True)

    convert_clip_to_safetensors(tmp_path)

    after = load_file(str(tmp_path / 'model.safetensors'))
    assert set(after) == set(before)
    assert all(torch.equal(after[name], before[name]) for name in before)
