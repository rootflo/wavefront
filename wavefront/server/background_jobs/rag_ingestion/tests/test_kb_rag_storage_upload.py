"""
Tests for KBRagStorage's upload retry policy against floware. httpx.post and
time.sleep are patched, so no network calls or real waits happen.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from rag_ingestion.service import kb_rag_storage
from rag_ingestion.service.kb_rag_storage import EmbeddingsRejectedError, KBRagStorage


def response(status_code: int) -> MagicMock:
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status_code
    mock.text = f'status {status_code}'
    return mock


@pytest.fixture
def storage():
    with patch.object(kb_rag_storage, 'EmbeddingFunc'):
        return KBRagStorage()


def upload_with_responses(storage, *responses):
    with (
        patch.object(kb_rag_storage.httpx, 'post', side_effect=list(responses)) as post,
        patch.object(kb_rag_storage.time, 'sleep'),
    ):
        try:
            result = storage._upload_doc_wise_embeddings([{'document_id': 'd1'}])
        finally:
            calls = post.call_count
    return result, calls


def test_success_on_first_attempt(storage):
    result, calls = upload_with_responses(storage, response(200))

    assert result.status_code == 200
    assert calls == 1


def test_server_errors_are_retried(storage):
    result, calls = upload_with_responses(storage, response(503), response(200))

    assert result.status_code == 200
    assert calls == 2


def test_rate_limit_is_retried(storage):
    result, calls = upload_with_responses(storage, response(429), response(200))

    assert calls == 2


@pytest.mark.parametrize('status_code', [400, 404, 422])
def test_client_errors_are_not_retried(storage, status_code):
    with (
        patch.object(
            kb_rag_storage.httpx, 'post', return_value=response(status_code)
        ) as post,
        patch.object(kb_rag_storage.time, 'sleep'),
        pytest.raises(EmbeddingsRejectedError),
    ):
        storage._upload_doc_wise_embeddings([{'document_id': 'd1'}])

    assert post.call_count == 1


def test_gives_up_after_max_retries(storage):
    with (
        patch.object(kb_rag_storage.httpx, 'post', return_value=response(500)) as post,
        patch.object(kb_rag_storage.time, 'sleep'),
        pytest.raises(Exception, match='after max retries'),
    ):
        storage._upload_doc_wise_embeddings([{'document_id': 'd1'}], max_retries=3)

    assert post.call_count == 3
