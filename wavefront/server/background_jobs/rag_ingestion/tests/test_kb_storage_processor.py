"""
Tests for KbStorageProcessor's failure handling and FileProcessor's image type
gate. Cloud storage, the inference service and floware are all mocked.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from flo_utils.streaming.message_processor import ProcessingResult
from rag_ingestion.models.doc_content import DocContent
from rag_ingestion.models.knowledge_base_embeddings import (
    KnowledgeBaseEmbeddingObject,
)
from rag_ingestion.processors import kb_storage_processor
from rag_ingestion.processors.file_processor import DocumentType, FileProcessor
from rag_ingestion.processors.kb_storage_processor import (
    KbStorageInsights,
    KbStorageProcessor,
)

EMBEDDING = KnowledgeBaseEmbeddingObject(
    embedding_vector=[0.1],
    embedding_vector_1=[0.2],
    chunk_text='image data',
    chunk_index='chunk_0',
)


def fake_embed_image(content: bytes) -> KnowledgeBaseEmbeddingObject:
    if content == b'bad':
        raise RuntimeError('inference service returned 400')
    return EMBEDDING


@pytest.fixture
def processor():
    with (
        patch.object(kb_storage_processor, 'KBRagStorage'),
        patch.object(kb_storage_processor, 'EmbeddingFunc'),
        patch.object(kb_storage_processor, 'ImageEmbedding'),
    ):
        processor = KbStorageProcessor(
            storage_manager=MagicMock(), encryption_service=None
        )
    processor.image_embedding.embed_image.side_effect = fake_embed_image
    processor.kb_rag_storage.process_document.return_value = [EMBEDDING]
    return processor


def make_insight(doc_id: str, document_type: DocumentType, content):
    return ProcessingResult[KbStorageInsights](
        success=True,
        insights=KbStorageInsights(
            doc_id=doc_id,
            doc_content=DocContent(content=content, document_type=document_type),
            kb_id='kb-1',
            file_type=document_type,
        ),
    )


def uploaded_doc_ids(processor) -> list:
    call = processor.kb_rag_storage.upload_embedding_with_retry.call_args
    return sorted(e.doc_id for e in call.kwargs['embeddings'])


def make_message(file_type: str, doc_id: str = 'doc-1'):
    return SimpleNamespace(
        id='msg-1',
        bucket_name='bucket',
        bucket_key='key',
        doc_id=doc_id,
        kb_id='kb-1',
        file_type=file_type,
    )


class TestStore:
    def test_failed_image_is_marked_failed_and_rest_uploaded(self, processor):
        bad = make_insight('d1', DocumentType.IMAGE, b'bad')
        image = make_insight('d2', DocumentType.IMAGE, b'ok')
        text = make_insight('d3', DocumentType.TEXT, 'some text')

        assert processor.store([bad, image, text]) is True

        assert uploaded_doc_ids(processor) == ['d2', 'd3']
        assert bad.success is False
        assert 'inference service returned 400' in bad.error
        assert image.success is True and text.success is True

    def test_all_failed_skips_upload_and_marks_each_failed(self, processor):
        insights = [
            make_insight('d1', DocumentType.IMAGE, b'bad'),
            make_insight('d2', DocumentType.IMAGE, b'bad'),
        ]

        assert processor.store(insights) is True

        processor.kb_rag_storage.upload_embedding_with_retry.assert_not_called()
        assert all(insight.success is False for insight in insights)

    def test_upload_failure_fails_the_batch(self, processor):
        processor.kb_rag_storage.upload_embedding_with_retry.side_effect = Exception(
            'floware unavailable'
        )

        assert processor.store([make_insight('d1', DocumentType.IMAGE, b'ok')]) is False

    def test_empty_batch_returns_false(self, processor):
        assert processor.store([]) is False


class TestProcess:
    async def test_supported_image_is_extracted(self, processor):
        processor.storage_manager.read_file.return_value = b'png-bytes'

        result = await processor.process(make_message('image/png'))

        assert result.success is True
        assert result.insights.doc_content.content == b'png-bytes'
        assert result.insights.file_type == DocumentType.IMAGE

    async def test_unsupported_image_type_fails_only_this_message(self, processor):
        processor.storage_manager.read_file.return_value = b'<svg/>'

        result = await processor.process(make_message('image/svg+xml'))

        assert result.success is False
        assert 'Unsupported image type' in result.error

    async def test_storage_read_failure_fails_only_this_message(self, processor):
        processor.storage_manager.read_file.side_effect = Exception('bucket down')

        result = await processor.process(make_message('image/png'))

        assert result.success is False
        assert 'bucket down' in result.error


class TestExtractDocumentType:
    @pytest.mark.parametrize(
        'mime_type',
        ['image/png', 'image/jpeg', 'image/webp', 'image/tiff', 'image/jpeg; q=1'],
    )
    def test_supported_image_types(self, mime_type):
        assert FileProcessor().extract_document_type(mime_type) == DocumentType.IMAGE

    @pytest.mark.parametrize('mime_type', ['image/svg+xml', 'image/heic', 'image/avif'])
    def test_unsupported_image_types_are_rejected(self, mime_type):
        with pytest.raises(ValueError, match='Unsupported image type'):
            FileProcessor().extract_document_type(mime_type)
