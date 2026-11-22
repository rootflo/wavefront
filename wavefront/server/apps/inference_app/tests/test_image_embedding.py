"""
ImageEmbedding with tiny randomly initialised CLIP and DINOv3 models, so the
real transformers forward passes run without a download.
"""

import io
import threading

import pytest

torch = pytest.importorskip('torch')

from PIL import Image  # noqa: E402
from transformers import (  # noqa: E402
    CLIPConfig,
    CLIPImageProcessor,
    CLIPModel,
    DINOv3ViTConfig,
    DINOv3ViTModel,
)

from inference_app.service.image_embedding import ImageEmbedding  # noqa: E402

PROJECTION_DIM = 16
DINO_HIDDEN = 32


def tiny_embedder() -> ImageEmbedding:
    torch.manual_seed(0)
    layer = {
        'hidden_size': 32,
        'intermediate_size': 37,
        'num_hidden_layers': 1,
        'num_attention_heads': 2,
    }
    clip = CLIPModel(
        CLIPConfig(
            text_config={**layer, 'vocab_size': 99},
            vision_config={**layer, 'image_size': 32, 'patch_size': 16},
            projection_dim=PROJECTION_DIM,
        )
    ).eval()
    dino = DINOv3ViTModel(
        DINOv3ViTConfig(
            hidden_size=DINO_HIDDEN,
            intermediate_size=64,
            num_hidden_layers=1,
            num_attention_heads=2,
            image_size=32,
            patch_size=16,
        )
    ).eval()
    processor = CLIPImageProcessor(
        size={'shortest_edge': 32}, crop_size={'height': 32, 'width': 32}
    )

    embedder = ImageEmbedding.__new__(ImageEmbedding)
    embedder.device = torch.device('cpu')
    embedder._model_lock = threading.Lock()
    embedder.clip_processor = embedder.dino_processor = processor
    embedder.clip_model = clip
    embedder.dino_model = dino
    embedder.embedders = {
        'clip': {
            'processor': processor,
            'model': clip,
            'extractor': embedder._extract_clip_features,
        },
        'dino': {
            'processor': processor,
            'model': dino,
            'extractor': embedder._extract_dino_features,
        },
    }
    return embedder


def png(color) -> bytes:
    buf = io.BytesIO()
    Image.new('RGB', (40, 40), color).save(buf, format='PNG')
    return buf.getvalue()


def test_clip_features_are_the_projected_image_embedding():
    embedder = tiny_embedder()
    pixel_values = embedder.clip_processor(
        images=Image.open(io.BytesIO(png('red'))), return_tensors='pt'
    )['pixel_values']

    with torch.inference_mode():
        features = embedder._extract_clip_features({'pixel_values': pixel_values})
        pooled = embedder.clip_model.vision_model(pixel_values).pooler_output
        expected = embedder.clip_model.visual_projection(pooled)

    assert isinstance(features, torch.Tensor)
    assert torch.allclose(features, expected)


def test_query_embed_batch_returns_unit_vectors_per_image():
    embedder = tiny_embedder()

    [clip, dino] = embedder.query_embed_batch([png('red'), png('blue')])

    assert len(clip['clip']) == len(dino['dino']) == 2
    assert all(len(v) == PROJECTION_DIM for v in clip['clip'])
    assert all(len(v) == DINO_HIDDEN for v in dino['dino'])
    for vector in clip['clip'] + dino['dino']:
        assert sum(x * x for x in vector) == pytest.approx(1.0, rel=1e-4)


def test_query_embed_returns_unit_vectors():
    embedder = tiny_embedder()

    [clip, dino] = embedder.query_embed(png('green'))

    assert len(clip['clip']) == PROJECTION_DIM
    assert len(dino['dino']) == DINO_HIDDEN
    assert sum(x * x for x in clip['clip']) == pytest.approx(1.0, rel=1e-4)
