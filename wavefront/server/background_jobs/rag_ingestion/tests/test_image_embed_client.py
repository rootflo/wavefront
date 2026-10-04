"""
Tests for the rag_ingestion image embedding client: batching, retries and
per-image fallback. The inference service is replaced by an httpx
MockTransport, so no network calls are made.
"""

import base64
import json
from typing import Callable, List

import httpx
import pytest

from rag_ingestion.embeddings import image_embed, inference_http
from rag_ingestion.embeddings.image_embed import ImageEmbedding

BATCH_PATH = '/inference/v1/query/embeddings/batch'
SINGLE_PATH = '/inference/v1/query/embeddings'


def vector_for(content: bytes) -> List[float]:
    """A deterministic 'embedding' so tests can check ordering."""
    return [float(len(content)), float(content[0])]


def ok_response(contents: List[bytes], batch: bool) -> httpx.Response:
    if batch:
        clip = [vector_for(c) for c in contents]
        dino = [[-v for v in vector_for(c)] for c in contents]
    else:
        clip = vector_for(contents[0])
        dino = [-v for v in vector_for(contents[0])]
    return httpx.Response(
        200, json={'data': {'response': [{'clip': clip}, {'dino': dino}]}}
    )


class FakeInferenceService:
    """Records requests and answers like the inference app.

    Images equal to b'bad' fail to decode (400). `batch_responses` can script
    the first few batch responses (status codes or exceptions to raise).
    """

    def __init__(self, max_batch_size: int = 8, batch_responses=()):
        self.max_batch_size = max_batch_size
        self.batch_responses = list(batch_responses)
        self.batch_sizes: List[int] = []
        self.single_calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if request.url.path == BATCH_PATH:
            contents = [base64.b64decode(i) for i in body['image_batch']]
            self.batch_sizes.append(len(contents))
            if self.batch_responses:
                scripted = self.batch_responses.pop(0)
                if isinstance(scripted, Exception):
                    raise scripted
                return httpx.Response(scripted, json={'error': 'scripted'})
            if len(contents) > self.max_batch_size:
                return httpx.Response(413, json={'error': 'batch too large'})
            if b'bad' in contents:
                return httpx.Response(400, json={'error': 'cannot decode image'})
            return ok_response(contents, batch=True)

        assert request.url.path == SINGLE_PATH
        self.single_calls += 1
        content = base64.b64decode(body['image_data'])
        if content == b'bad':
            return httpx.Response(400, json={'error': 'cannot decode image'})
        return ok_response([content], batch=False)


@pytest.fixture
def make_client(monkeypatch) -> Callable[..., ImageEmbedding]:
    monkeypatch.setattr(image_embed, 'INFERENCE_SERVICE_URL', 'http://inference')

    def factory(service: FakeInferenceService, batch_size: int = 8) -> ImageEmbedding:
        client = ImageEmbedding(batch_size=batch_size, initial_delay=0)
        client._client = httpx.Client(transport=httpx.MockTransport(service))
        return client

    return factory


def embeddings_of(results):
    return [r.embedding.embedding_vector for r in results]


def test_images_are_sent_in_chunks_of_batch_size_and_kept_in_order(make_client):
    service = FakeInferenceService()
    client = make_client(service, batch_size=2)
    images = [b'a', b'bb', b'ccc', b'dddd', b'eeeee']

    results = client.embed_images(images)

    assert service.batch_sizes == [2, 2, 1]
    assert service.single_calls == 0
    assert all(r.error is None for r in results)
    assert embeddings_of(results) == [vector_for(i) for i in images]
    assert results[0].embedding.embedding_vector_1 == [-1.0, -97.0]


def test_bad_image_fails_alone_via_per_image_fallback(make_client):
    service = FakeInferenceService()
    client = make_client(service)

    results = client.embed_images([b'a', b'bad', b'c'])

    assert service.batch_sizes == [3]
    assert service.single_calls == 3
    assert results[0].embedding.embedding_vector == vector_for(b'a')
    assert isinstance(results[1].error, httpx.HTTPStatusError)
    assert results[1].error.response.status_code == 400
    assert results[2].embedding.embedding_vector == vector_for(b'c')


def test_batch_over_service_limit_falls_back_to_single_calls(make_client):
    service = FakeInferenceService(max_batch_size=2)
    client = make_client(service, batch_size=4)

    results = client.embed_images([b'a', b'b', b'c'])

    assert service.batch_sizes == [3]
    assert service.single_calls == 3
    assert all(r.error is None for r in results)


def test_transient_server_errors_are_retried(make_client):
    service = FakeInferenceService(batch_responses=[503, 502])
    client = make_client(service)

    results = client.embed_images([b'a', b'b'])

    assert service.batch_sizes == [2, 2, 2]
    assert all(r.error is None for r in results)


def test_persistent_server_error_fails_the_chunk_without_fallback(make_client):
    service = FakeInferenceService(batch_responses=[503, 503, 503])
    client = make_client(service)

    results = client.embed_images([b'a', b'b'])

    assert service.batch_sizes == [2, 2, 2]
    assert service.single_calls == 0
    assert all(isinstance(r.error, httpx.HTTPStatusError) for r in results)


def test_connection_errors_are_retried(make_client):
    service = FakeInferenceService(
        batch_responses=[httpx.ConnectError('connection refused')]
    )
    client = make_client(service)

    results = client.embed_images([b'a'])

    assert service.batch_sizes == [1, 1]
    assert results[0].error is None


def test_read_timeout_is_not_retried(make_client):
    service = FakeInferenceService(batch_responses=[httpx.ReadTimeout('slow')])
    client = make_client(service)

    results = client.embed_images([b'a', b'b'])

    assert service.batch_sizes == [2]
    assert all(isinstance(r.error, httpx.ReadTimeout) for r in results)


def test_failure_in_one_chunk_does_not_affect_other_chunks(make_client):
    service = FakeInferenceService(batch_responses=[500])
    client = make_client(service, batch_size=2)

    results = client.embed_images([b'a', b'b', b'c'])

    assert service.batch_sizes == [2, 1]
    assert [r.error is not None for r in results] == [True, True, False]


def test_response_with_wrong_count_fails_the_chunk(make_client):
    def short_response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={'data': {'response': [{'clip': [[1.0]]}, {'dino': [[1.0]]}]}}
        )

    client = make_client(FakeInferenceService())
    client._client = httpx.Client(transport=httpx.MockTransport(short_response))

    results = client.embed_images([b'a', b'b'])

    assert all(isinstance(r.error, ValueError) for r in results)


def test_empty_input_makes_no_calls(make_client):
    service = FakeInferenceService()

    assert make_client(service).embed_images([]) == []
    assert service.batch_sizes == []


def rate_limited_then_ok(retry_after: str):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={'Retry-After': retry_after})
        contents = [
            base64.b64decode(i) for i in json.loads(request.content)['image_batch']
        ]
        return ok_response(contents, batch=True)

    return handler, calls


@pytest.mark.parametrize(
    ('retry_after', 'expected_wait'),
    [('2', 2.0), ('500', 60.0), ('soon', 0.0)],
)
def test_429_waits_for_retry_after_capped_at_60s(
    make_client, monkeypatch, retry_after, expected_wait
):
    sleeps = []
    monkeypatch.setattr(inference_http.time, 'sleep', sleeps.append)
    handler, calls = rate_limited_then_ok(retry_after)
    client = make_client(FakeInferenceService())
    client._client = httpx.Client(transport=httpx.MockTransport(handler))

    results = client.embed_images([b'a'])

    assert len(calls) == 2
    assert results[0].error is None
    # initial_delay is 0 in these tests, so any wait comes from Retry-After
    assert sleeps == [expected_wait]
