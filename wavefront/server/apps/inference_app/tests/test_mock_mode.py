"""
Mock mode: where torch isn't installed (Intel Macs) the inference app serves
synthetic embeddings with the real shapes and formats, for integration
testing. None of these tests need torch.
"""

import base64
import io
import math

import pytest
from dependency_injector import providers
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from inference_app import mock
from inference_app.rate_limiter import SlidingWindowRateLimiter
from inference_app.service.mock_embeddings import (
    CLIP_DIM,
    DINO_DIM,
    TEXT_DENSE_DIM,
    TEXT_SPARSE_DIM,
    MockImageEmbedding,
    MockTextEmbedding,
)


def image_bytes(shape='square', color='red', fmt='PNG') -> bytes:
    image = Image.new('RGB', (64, 64), 'white')
    draw = ImageDraw.Draw(image)
    (draw.rectangle if shape == 'square' else draw.ellipse)((8, 8, 56, 56), fill=color)
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def norm(vector) -> float:
    return math.sqrt(sum(v * v for v in vector))


def cosine(a, b) -> float:
    return sum(x * y for x, y in zip(a, b)) / (norm(a) * norm(b))


# --- deciding mock mode ------------------------------------------------------


@pytest.mark.parametrize(
    ('setting', 'torch_installed', 'expected'),
    [
        ('auto', False, True),
        ('auto', True, False),
        ('true', True, True),
        ('false', False, False),
    ],
)
def test_mock_mode_decision(monkeypatch, setting, torch_installed, expected):
    monkeypatch.setattr(mock, 'torch_available', lambda: torch_installed)

    assert mock.use_mock_models(setting) is expected


# --- mock image model ----------------------------------------------------------


def test_image_vectors_have_real_shapes_and_are_unit_length():
    clip, dino = MockImageEmbedding().query_embed(image_bytes())

    assert len(clip['clip']) == CLIP_DIM and len(dino['dino']) == DINO_DIM
    assert norm(clip['clip']) == pytest.approx(1.0)
    assert norm(dino['dino']) == pytest.approx(1.0)


def test_same_picture_gives_the_same_vectors_even_re_encoded():
    model = MockImageEmbedding()

    as_png = model.query_embed(image_bytes(fmt='PNG'))
    as_bmp = model.query_embed(image_bytes(fmt='BMP'))

    assert as_png == as_bmp


def test_different_pictures_give_different_vectors():
    model = MockImageEmbedding()

    square = model.query_embed(image_bytes('square'))[0]['clip']
    circle = model.query_embed(image_bytes('circle'))[0]['clip']

    assert cosine(square, circle) < 0.5


def test_batch_matches_single_and_keeps_order():
    model = MockImageEmbedding()
    images = [image_bytes('square'), image_bytes('circle', 'blue')]

    [clips, dinos] = model.query_embed_batch(images)

    assert clips['clip'] == [model.query_embed(i)[0]['clip'] for i in images]
    assert dinos['dino'] == [model.query_embed(i)[1]['dino'] for i in images]


def test_undecodable_images_raise_like_the_real_model():
    model = MockImageEmbedding()

    with pytest.raises(ValueError, match='Failed to decode image'):
        model.query_embed(b'not an image')
    with pytest.raises(ValueError, match='index 1'):
        model.query_embed_batch([image_bytes(), b'not an image'])


# --- mock text model -----------------------------------------------------------


def test_text_outputs_have_real_shapes():
    model = MockTextEmbedding()

    [result] = model.embed(['Tomatoes need sunlight'])

    assert len(result['dense']) == TEXT_DENSE_DIM == model.dense_dim
    assert norm(result['dense']) == pytest.approx(1.0)
    indices = result['sparse']['indices']
    assert indices == sorted(set(indices))
    assert all(4 <= i < TEXT_SPARSE_DIM for i in indices)  # no special tokens
    assert len(result['sparse']['values']) == len(indices)
    assert model.sparse_dim == TEXT_SPARSE_DIM


def test_texts_sharing_words_score_higher():
    model = MockTextEmbedding()
    [doc, related, unrelated] = model.embed(
        [
            'tomatoes need six hours of sunlight',
            'how much sunlight do tomatoes need',
            'quarterly revenue grew in europe',
        ]
    )

    assert cosine(doc['dense'], related['dense']) > cosine(
        doc['dense'], unrelated['dense']
    )
    shared = set(doc['sparse']['indices']) & set(related['sparse']['indices'])
    assert len(shared) >= 3


def test_text_similarity_has_a_bge_like_baseline():
    model = MockTextEmbedding()
    [a, b, same] = model.embed(
        ['alpha beta gamma', 'delta epsilon zeta', 'alpha beta gamma']
    )

    # unrelated ~0.5 (like real BGE-M3), identical 1.0
    assert cosine(a['dense'], b['dense']) == pytest.approx(0.5, abs=0.1)
    assert cosine(a['dense'], same['dense']) == pytest.approx(1.0)


def test_text_is_deterministic_and_respects_flags():
    model = MockTextEmbedding()

    assert model.embed(['same text']) == model.embed(['same text'])
    assert set(model.embed(['x'], return_sparse=False)[0]) == {'dense'}
    assert set(model.embed(['x'], return_dense=False)[0]) == {'sparse'}


def test_long_text_stays_within_the_sparse_index_limit():
    [result] = MockTextEmbedding().embed([' '.join(f'word{i}' for i in range(5000))])

    assert len(result['sparse']['indices']) <= 512


# --- the app in mock mode ----------------------------------------------------


@pytest.fixture
def mock_app(monkeypatch):
    from inference_app import server

    monkeypatch.setattr(server, 'MOCK_MODELS', True)
    container = server.inference_app_container
    with container.rate_limiter.override(
        providers.Object(SlidingWindowRateLimiter([]))
    ):
        with TestClient(server.app) as client:  # runs the lifespan
            yield client
    container.image_embedding.reset_override()
    container.text_embedding_provider.reset()


def test_app_starts_in_mock_mode_and_says_so(mock_app):
    assert mock_app.get('/inference/v1/health').json() == {
        'status': 'ok',
        'mock_models': True,
    }


def test_image_endpoints_work_in_mock_mode(mock_app):
    encoded = base64.b64encode(image_bytes()).decode('ascii')

    single = mock_app.post(
        '/inference/v1/query/embeddings', json={'image_data': encoded}
    )
    batch = mock_app.post(
        '/inference/v1/query/embeddings/batch', json={'image_batch': [encoded, encoded]}
    )

    assert single.status_code == 200
    [clip, dino] = single.json()['data']['response']
    assert len(clip['clip']) == CLIP_DIM and len(dino['dino']) == DINO_DIM
    assert batch.status_code == 200
    assert len(batch.json()['data']['response'][0]['clip']) == 2


def test_text_endpoint_works_in_mock_mode(mock_app):
    response = mock_app.post(
        '/inference/v1/query/text-embeddings', json={'texts': ['hello world', 'bye']}
    )

    assert response.status_code == 200
    data = response.json()['data']
    assert (data['dense_dim'], data['sparse_dim']) == (TEXT_DENSE_DIM, TEXT_SPARSE_DIM)
    assert len(data['response']) == 2
