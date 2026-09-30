"""
Tests for the embedding endpoints: the batch size limit, how bad input is
reported, and the rate limit. The embedding service is a fake, so no models
load.
"""

import base64

import pytest

pytest.importorskip('torch')

from dependency_injector import providers  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from inference_app.controllers import inference_controller  # noqa: E402
from inference_app.rate_limiter import SlidingWindowRateLimiter  # noqa: E402

BATCH_URL = '/inference/v1/query/embeddings/batch'
SINGLE_URL = '/inference/v1/query/embeddings'
HEALTH_URL = '/inference/v1/health'


class FakeEmbedding:
    def __init__(self):
        self.batches = []

    def query_embed(self, image_content):
        return [{'clip': [1.0]}, {'dino': [2.0]}]

    def query_embed_batch(self, image_batch):
        self.batches.append(image_batch)
        if b'bad' in image_batch:
            raise ValueError(
                f'Failed to decode image at index {image_batch.index(b"bad")}'
            )
        return [
            {'clip': [[1.0] for _ in image_batch]},
            {'dino': [[2.0] for _ in image_batch]},
        ]


def make_client(rate_limiter: SlidingWindowRateLimiter):
    from inference_app import server

    fake = FakeEmbedding()
    container = server.inference_app_container
    with (
        container.image_embedding.override(providers.Object(fake)),
        container.rate_limiter.override(providers.Object(rate_limiter)),
    ):
        yield TestClient(server.app), fake


@pytest.fixture
def client_and_service(monkeypatch):
    monkeypatch.setattr(inference_controller, 'MAX_EMBEDDING_BATCH_SIZE', 3)
    yield from make_client(SlidingWindowRateLimiter([]))


@pytest.fixture
def rate_limited_client():
    yield from make_client(SlidingWindowRateLimiter([(2, 60.0)]))


def encode(*images: bytes):
    return {'image_batch': [base64.b64encode(i).decode('ascii') for i in images]}


def test_batch_within_limit_is_embedded(client_and_service):
    client, fake = client_and_service

    response = client.post(BATCH_URL, json=encode(b'a', b'b', b'c'))

    assert response.status_code == 200
    assert response.json()['data']['response'] == [
        {'clip': [[1.0], [1.0], [1.0]]},
        {'dino': [[2.0], [2.0], [2.0]]},
    ]
    assert fake.batches == [[b'a', b'b', b'c']]


def test_batch_over_limit_is_rejected_before_embedding(client_and_service):
    client, fake = client_and_service

    response = client.post(BATCH_URL, json=encode(b'a', b'b', b'c', b'd'))

    assert response.status_code == 413
    assert 'maximum of 3' in response.text
    assert fake.batches == []


def test_empty_batch_is_rejected(client_and_service):
    client, fake = client_and_service

    response = client.post(BATCH_URL, json={'image_batch': []})

    assert response.status_code == 400
    assert fake.batches == []


def test_undecodable_image_returns_400_naming_it(client_and_service):
    client, _ = client_and_service

    response = client.post(BATCH_URL, json=encode(b'a', b'bad'))

    assert response.status_code == 400
    assert 'index 1' in response.text


def test_invalid_base64_returns_400(client_and_service):
    client, fake = client_and_service

    response = client.post(BATCH_URL, json={'image_batch': ['not-base64!']})

    assert response.status_code == 400
    assert fake.batches == []


def test_requests_over_the_rate_limit_get_429_with_retry_after(rate_limited_client):
    client, fake = rate_limited_client

    statuses = [client.post(BATCH_URL, json=encode(b'a')).status_code for _ in range(2)]
    limited = client.post(BATCH_URL, json=encode(b'a'))

    assert statuses == [200, 200]
    assert limited.status_code == 429
    assert 1 <= int(limited.headers['Retry-After']) <= 60
    assert len(fake.batches) == 2


def test_rate_limit_is_shared_by_single_and_batch_endpoints(rate_limited_client):
    client, _ = rate_limited_client
    single = {'image_data': base64.b64encode(b'a').decode('ascii')}

    assert client.post(SINGLE_URL, json=single).status_code == 200
    assert client.post(BATCH_URL, json=encode(b'a')).status_code == 200
    assert client.post(SINGLE_URL, json=single).status_code == 429


def test_health_check_is_not_rate_limited(rate_limited_client):
    client, _ = rate_limited_client
    for _ in range(3):
        client.post(BATCH_URL, json=encode(b'a'))

    assert all(client.get(HEALTH_URL).status_code == 200 for _ in range(5))
