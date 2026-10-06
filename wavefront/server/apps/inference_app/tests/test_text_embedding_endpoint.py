"""
Tests for /inference/v1/query/text-embeddings and for BGE-M3 being optional at
startup. The model is a fake; no weights load.
"""

import threading

import pytest

from dependency_injector import providers  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from inference_app.middleware.rate_limiter import SlidingWindowRateLimiter  # noqa: E402
from inference_app.service.text_embedding_provider import TextEmbeddingProvider  # noqa: E402

URL = '/inference/v1/query/text-embeddings'


class FakeTextModel:
    dense_dim = 3
    sparse_dim = 100

    def __init__(self):
        self.calls = []

    def embed(self, texts, return_dense=True, return_sparse=True):
        self.calls.append((texts, return_dense, return_sparse))
        results = []
        for i, _ in enumerate(texts):
            result = {}
            if return_dense:
                result['dense'] = [float(i), 0.0, 1.0]
            if return_sparse:
                result['sparse'] = {'indices': [i + 5], 'values': [0.5]}
            results.append(result)
        return results


def ready_provider(model):
    provider = TextEmbeddingProvider()
    provider.load(lambda: model)
    return provider


def make_client(
    provider, rate_limiter=None, *, max_text_embedding_batch_size: str = '16'
):
    from inference_app import server

    container = server.application_container
    with (
        container.text_embedding_provider.override(providers.Object(provider)),
        container.rate_limiter.override(
            providers.Object(rate_limiter or SlidingWindowRateLimiter([]))
        ),
        container.config.inference.max_text_embedding_batch_size.override(
            max_text_embedding_batch_size
        ),
    ):
        yield TestClient(server.app)


@pytest.fixture
def fake_model():
    return FakeTextModel()


@pytest.fixture
def client(fake_model):
    yield from make_client(
        ready_provider(fake_model), max_text_embedding_batch_size='3'
    )


def test_returns_dense_and_sparse_per_text(client, fake_model):
    response = client.post(URL, json={'texts': ['first', 'second']})

    assert response.status_code == 200
    data = response.json()['data']
    assert data['model'] == 'bge-m3'
    assert (data['dense_dim'], data['sparse_dim']) == (3, 100)
    assert data['response'] == [
        {'dense': [0.0, 0.0, 1.0], 'sparse': {'indices': [5], 'values': [0.5]}},
        {'dense': [1.0, 0.0, 1.0], 'sparse': {'indices': [6], 'values': [0.5]}},
    ]
    assert fake_model.calls == [(['first', 'second'], True, True)]


@pytest.mark.parametrize(
    ('flags', 'keys'),
    [({'return_sparse': False}, {'dense'}), ({'return_dense': False}, {'sparse'})],
)
def test_can_request_only_one_kind(client, flags, keys):
    response = client.post(URL, json={'texts': ['a'], **flags})

    assert set(response.json()['data']['response'][0]) == keys


def test_requesting_neither_kind_is_rejected(client, fake_model):
    response = client.post(
        URL, json={'texts': ['a'], 'return_dense': False, 'return_sparse': False}
    )

    assert response.status_code == 400
    assert fake_model.calls == []


def test_empty_batch_is_rejected(client):
    assert client.post(URL, json={'texts': []}).status_code == 400


def test_batch_over_limit_is_rejected(client, fake_model):
    response = client.post(URL, json={'texts': ['a', 'b', 'c', 'd']})

    assert response.status_code == 413
    assert 'maximum of 3' in response.text
    assert fake_model.calls == []


@pytest.mark.parametrize(
    ('setup', 'message'),
    [
        (lambda p: None, 'not enabled'),
        (
            lambda p: setattr(p, 'status', TextEmbeddingProvider.LOADING),
            'still loading',
        ),
        (
            lambda p: p.load(lambda: (_ for _ in ()).throw(OSError('no weights'))),
            'no weights',
        ),
    ],
)
def test_unavailable_model_returns_503_with_reason(setup, message):
    provider = TextEmbeddingProvider()
    setup(provider)

    for client in make_client(provider):
        response = client.post(URL, json={'texts': ['a']})

    assert response.status_code == 503
    assert message in response.text


def test_text_embeddings_share_the_rate_limit():
    for client in make_client(
        ready_provider(FakeTextModel()), SlidingWindowRateLimiter([(1, 60.0)])
    ):
        assert client.post(URL, json={'texts': ['a']}).status_code == 200
        assert client.post(URL, json={'texts': ['a']}).status_code == 429


class TestStartup:
    @pytest.fixture
    def fresh_provider(self):
        from inference_app import server
        from inference_app.models import setup as models_setup

        provider = TextEmbeddingProvider()
        with server.application_container.text_embedding_provider.override(
            providers.Object(provider)
        ):
            yield models_setup, provider

    def test_unset_uri_leaves_text_embeddings_disabled(
        self, fresh_provider, monkeypatch
    ):
        models_setup, provider = fresh_provider
        monkeypatch.setattr(models_setup, 'BGE_M3_MODEL_URI', '')
        loader_called = []
        monkeypatch.setattr(
            models_setup, 'load_text_embedding_model', lambda: loader_called.append(1)
        )

        models_setup.start_text_embedding_model()

        assert provider.status == 'disabled'
        assert loader_called == []

    def test_failed_load_does_not_stop_startup(self, fresh_provider, monkeypatch):
        models_setup, provider = fresh_provider
        monkeypatch.setattr(models_setup, 'BGE_M3_MODEL_URI', 's3://bucket/bge-m3')
        done = threading.Event()

        def broken_loader():
            try:
                raise ValueError('No objects found at cloud URI')
            finally:
                done.set()

        monkeypatch.setattr(models_setup, 'load_text_embedding_model', broken_loader)

        models_setup.start_text_embedding_model()  # must not raise

        assert done.wait(timeout=5)
        for _ in range(50):
            if provider.status == 'failed':
                break
            threading.Event().wait(0.01)
        assert provider.status == 'failed'
        assert 'No objects found' in provider.error


@pytest.mark.parametrize(
    ('setup', 'retry_after'),
    [
        (lambda p: setattr(p, 'status', TextEmbeddingProvider.LOADING), '10'),
        (lambda p: None, None),
        (lambda p: p.load(lambda: (_ for _ in ()).throw(OSError('no weights'))), None),
    ],
)
def test_retry_after_is_sent_only_while_the_model_loads(setup, retry_after):
    # Clients (rag_ingestion) honour it, so they wait out a loading model; a
    # disabled or failed model won't recover by waiting.
    provider = TextEmbeddingProvider()
    setup(provider)

    for client in make_client(provider):
        response = client.post(URL, json={'texts': ['a']})

    assert response.status_code == 503
    assert response.headers.get('retry-after') == retry_after
