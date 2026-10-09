"""
Tests for the text embedding client in rag_ingestion: batching (one request
per batch, every batch covered), the BGE-M3 request it sends to the inference
app, response validation, and retries. The inference app is an httpx
MockTransport, so no network calls are made.
"""

import json
from unittest.mock import patch

import httpx
import pytest

from rag_ingestion.embeddings import embed, inference_http
from rag_ingestion.embeddings.embed import EmbeddingFunc
from rag_ingestion.service import kb_rag_storage
from rag_ingestion.service.kb_rag_storage import KBRagStorage
from common_module.runtime_settings import RuntimeSettings


def vector_for(text: str):
    """A deterministic fake embedding, so ordering can be checked."""
    return [float(len(text)), float(sum(map(ord, text)) % 997)]


def sparse_for(text: str):
    return {'indices': [len(text)], 'values': [0.5]}


class FakeEmbeddingService:
    """Answers like the inference app's /inference/v1/query/text-embeddings.

    `script` holds responses to send first, in order: a status code (sent
    with `headers`), or an exception to raise.
    """

    def __init__(self, drop_last=False, dense_only=False, script=(), headers=None):
        self.drop_last = drop_last
        self.dense_only = dense_only
        self.script = list(script)
        self.headers = headers or {}
        self.batches = []
        self.requests = []
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.script:
            scripted = self.script.pop(0)
            if isinstance(scripted, Exception):
                raise scripted
            return httpx.Response(scripted, headers=self.headers, text='scripted')
        body = json.loads(request.content)
        texts = body['texts']
        self.batches.append(list(texts))
        self.requests.append((str(request.url), body))
        results = [
            {'dense': vector_for(text)}
            if self.dense_only
            else {'dense': vector_for(text), 'sparse': sparse_for(text)}
            for text in texts
        ]
        if self.drop_last:
            results = results[:-1]
        return httpx.Response(
            200,
            json={
                'meta': {'status': 'success'},
                'data': {'model': 'bge-m3', 'dense_dim': 2, 'response': results},
            },
        )


def make_chunks(count: int) -> dict:
    return {f'chunk_{i}': {'content': f'chunk text number {i}'} for i in range(count)}


def serve(service: FakeEmbeddingService):
    """Patch EmbeddingFunc's httpx.Client to answer from `service`."""
    real_client = httpx.Client

    def client_factory(**kwargs):
        return real_client(transport=httpx.MockTransport(service), **kwargs)

    return patch.object(embed.httpx, 'Client', client_factory)


INFERENCE_URL = 'http://inference:8003'


def make_func(**kwargs) -> EmbeddingFunc:
    return EmbeddingFunc(INFERENCE_URL, **kwargs)


@pytest.fixture
def sleeps(monkeypatch):
    waits = []
    monkeypatch.setattr(inference_http.time, 'sleep', waits.append)
    return waits


@pytest.fixture
def service():
    fake = FakeEmbeddingService()
    with serve(fake):
        yield fake


def test_every_chunk_is_embedded_in_batches_of_16(service):
    chunks = make_chunks(70)

    data_list, embeddings = make_func().generate_document_embeddings(chunks)

    assert [len(batch) for batch in service.batches] == [16, 16, 16, 16, 6]
    assert len(data_list) == len(embeddings) == 70
    for (key, chunk), item in zip(chunks.items(), data_list):
        assert item.chunk_index == key
        assert item.chunk_text == chunk['content']
        assert item.text_embedding == vector_for(chunk['content'])
        assert item.text_sparse_embedding == sparse_for(chunk['content'])
        assert item.embedding_vector == []


@pytest.mark.parametrize('count', [1, 15, 16, 17, 32, 33])
def test_batch_boundaries(service, count):
    data_list, _ = make_func().generate_document_embeddings(make_chunks(count))

    assert len(data_list) == count
    assert len(service.batches) == -(-count // 16)


def test_one_request_carries_the_whole_batch(service):
    make_func().generate_document_embeddings(make_chunks(5))

    assert service.batches == [[f'chunk text number {i}' for i in range(5)]]


def test_requests_bge_m3_dense_and_sparse_from_the_inference_app(service):
    make_func().generate_document_embeddings(make_chunks(2))

    [(url, payload)] = service.requests
    assert url == 'http://inference:8003/inference/v1/query/text-embeddings'
    assert payload == {
        'texts': ['chunk text number 0', 'chunk text number 1'],
        'return_dense': True,
        'return_sparse': True,
    }


def test_missing_embeddings_fail_loudly():
    with serve(FakeEmbeddingService(drop_last=True)):
        with pytest.raises(ValueError, match='Expected 3 embeddings'):
            make_func().generate_document_embeddings(make_chunks(3))


def test_result_missing_sparse_fails_loudly():
    with serve(FakeEmbeddingService(dense_only=True)):
        with pytest.raises(ValueError, match='missing dense or sparse'):
            make_func().generate_document_embeddings(make_chunks(1))


def test_no_chunks_makes_no_requests(service):
    assert make_func().generate_document_embeddings({}) == ([], [])
    assert service.batches == []


def test_long_document_is_fully_embedded_through_process_document(service):
    # ~60KB of text: well over 32 chunks at the 1,200-character chunk size
    paragraph = ' '.join(f'Sentence {i} about the knowledge base.' for i in range(30))
    text = '\n\n'.join(f'{paragraph} Paragraph {p}.' for p in range(50))
    with patch.object(kb_rag_storage, 'EmbeddingFunc', EmbeddingFunc):
        storage = KBRagStorage(
            inference_service_url=INFERENCE_URL,
            runtime_settings=RuntimeSettings(
                app_env='production',
                floware_base_url='http://localhost:8001',
                allowed_origins=('http://localhost:5173',),
                worker_count=1,
                uvicorn_log_level='critical',
            ),
        )

    docs = storage.process_document([text])

    assert len(docs) > 32
    assert len({d.chunk_index for d in docs}) == len(docs)
    assert all(d.text_embedding == vector_for(d.chunk_text) for d in docs)
    assert sum(len(batch) for batch in service.batches) == len(docs)
    assert all(len(batch) <= 16 for batch in service.batches)


# --- retries (item 11) -------------------------------------------------------


@pytest.mark.parametrize('status_code', [429, 502, 503, 504])
def test_transient_failures_are_retried(sleeps, status_code):
    fake = FakeEmbeddingService(script=[status_code])
    with serve(fake):
        data_list, _ = make_func().generate_document_embeddings(make_chunks(2))

    assert fake.calls == 2
    assert len(data_list) == 2
    assert sleeps == [1.0]


def test_retry_after_from_a_loading_model_is_honoured(sleeps):
    # The inference app answers 503 + Retry-After: 10 while BGE-M3 loads
    fake = FakeEmbeddingService(script=[503], headers={'Retry-After': '10'})
    with serve(fake):
        make_func().generate_document_embeddings(make_chunks(1))

    assert sleeps == [10.0]


def test_connection_errors_are_retried(sleeps):
    fake = FakeEmbeddingService(script=[httpx.ConnectError('refused')])
    with serve(fake):
        make_func().generate_document_embeddings(make_chunks(1))

    assert fake.calls == 2


def test_gives_up_after_three_attempts_with_backoff(sleeps):
    fake = FakeEmbeddingService(script=[503, 503, 503])
    with serve(fake):
        with pytest.raises(httpx.HTTPStatusError):
            make_func().generate_document_embeddings(make_chunks(1))

    assert fake.calls == 3
    assert sleeps == [1.0, 1.5]


@pytest.mark.parametrize('status_code', [400, 413, 422])
def test_client_errors_are_not_retried(sleeps, status_code):
    fake = FakeEmbeddingService(script=[status_code])
    with serve(fake):
        with pytest.raises(httpx.HTTPStatusError):
            make_func().generate_document_embeddings(make_chunks(1))

    assert fake.calls == 1
    assert sleeps == []


def test_read_timeouts_are_not_retried(sleeps):
    fake = FakeEmbeddingService(script=[httpx.ReadTimeout('slow')])
    with serve(fake):
        with pytest.raises(httpx.ReadTimeout):
            make_func().generate_document_embeddings(make_chunks(1))

    assert fake.calls == 1


def test_one_connection_pool_is_reused_across_batches(service):
    func = make_func()
    client = func._client

    func.generate_document_embeddings(make_chunks(40))

    assert func._client is client
    assert len(service.batches) == 3
