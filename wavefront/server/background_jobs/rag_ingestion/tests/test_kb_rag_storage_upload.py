"""
Tests for KBRagStorage's upload retry policy against floware. httpx.post and
time.sleep are patched, so no network calls or real waits happen.
"""

from unittest.mock import MagicMock, patch

import flo_lib.http as httpx
import pytest

from rag_ingestion.service import kb_rag_storage
from rag_ingestion.service.kb_rag_storage import EmbeddingsRejectedError, KBRagStorage
from common_module.runtime_settings import RuntimeSettings


def response(status_code: int) -> MagicMock:
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status_code
    mock.text = f'status {status_code}'
    return mock


@pytest.fixture
def storage():
    with patch.object(kb_rag_storage, 'EmbeddingFunc'):
        return KBRagStorage(
            inference_service_url='http://inference:8003',
            runtime_settings=RuntimeSettings(
                app_env='production',
                floware_base_url='http://localhost:8001',
                allowed_origins=('http://localhost:5173',),
                worker_count=1,
                uvicorn_log_level='critical',
            ),
        )


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


# --- payload shape ---------------------------------------------------------

from rag_ingestion.models.knowledge_base_embeddings import (  # noqa: E402
    KnowledgeBaseEmbeddingObject,
)
from rag_ingestion.processors.file_processor import DocumentType  # noqa: E402
from rag_ingestion.service.kb_rag_storage import EmbeddingsToStore  # noqa: E402


def captured_payload(storage, *documents):
    with patch.object(
        storage, '_upload_doc_wise_embeddings', return_value='ok'
    ) as upload:
        storage.upload_embedding_with_retry(embeddings=list(documents))
    return upload.call_args.args[0]


def test_text_documents_send_bge_m3_dense_and_sparse(storage):
    chunks = [
        KnowledgeBaseEmbeddingObject(
            chunk_text='first',
            chunk_index='chunk_0',
            text_embedding=[0.1, 0.2],
            text_sparse_embedding={'indices': [7], 'values': [0.4]},
        ),
        KnowledgeBaseEmbeddingObject(
            chunk_text='second', chunk_index='chunk_1', text_embedding=[0.3, 0.4]
        ),
    ]

    [payload] = captured_payload(
        storage, EmbeddingsToStore(chunks, 'doc-1', 'kb-1', DocumentType.PDF)
    )

    assert payload == {
        'document_id': 'doc-1',
        'kb_id': 'kb-1',
        'chunk_text': ['first', 'second'],
        'chunk_index': ['chunk_0', 'chunk_1'],
        'text_embedding': [[0.1, 0.2], [0.3, 0.4]],
        'text_sparse_embedding': [
            {'indices': [7], 'values': [0.4]},
            {'indices': [], 'values': []},
        ],
    }


def test_image_documents_send_clip_and_dino(storage):
    chunk = KnowledgeBaseEmbeddingObject(
        chunk_text='image data',
        chunk_index='chunk_0',
        embedding_vector=[0.5],
        embedding_vector_1=[0.6],
    )

    [payload] = captured_payload(
        storage, EmbeddingsToStore([chunk], 'doc-2', 'kb-2', DocumentType.IMAGE)
    )

    assert payload['embedding_vector'] == [[0.5]]
    assert payload['embedding_vector_1'] == [[0.6]]
    assert 'text_embedding' not in payload and 'text_sparse_embedding' not in payload
