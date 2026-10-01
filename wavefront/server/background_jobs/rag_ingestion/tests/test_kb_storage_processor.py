"""
Tests for KbStorageProcessor's failure handling and FileProcessor's image type
gate. Cloud storage, the inference service and floware are all mocked.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from db_repo_module.models.knowledge_base_documents import IndexStatus
from flo_utils.streaming.message_processor import ProcessingResult
from rag_ingestion.embeddings.image_embed import ImageEmbeddingResult
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


def fake_embed_images(contents: list) -> list:
    return [
        ImageEmbeddingResult(error=RuntimeError('inference service returned 400'))
        if content == b'bad'
        else ImageEmbeddingResult(embedding=EMBEDDING)
        for content in contents
    ]


@pytest.fixture
def processor():
    with (
        patch.object(kb_storage_processor, 'KBRagStorage'),
        patch.object(kb_storage_processor, 'EmbeddingFunc'),
        patch.object(kb_storage_processor, 'ImageEmbedding'),
    ):
        processor = KbStorageProcessor(
            storage_manager=MagicMock(),
            encryption_service=None,
            index_status_publisher=MagicMock(),
        )
    processor.index_status_publisher.publish.return_value = True
    processor.image_embedding.embed_images.side_effect = fake_embed_images
    processor.kb_rag_storage.process_document.return_value = [EMBEDDING]
    set_floware_rejections(processor, {})
    return processor


def set_floware_rejections(processor, reasons_by_doc_id: dict):
    """Make the mocked floware upload report these documents as rejected."""
    response = MagicMock()
    response.json.return_value = {
        'data': {
            'message': 'ok',
            'rejected': [
                {'document_id': doc_id, 'reason': reason}
                for doc_id, reason in reasons_by_doc_id.items()
            ],
        }
    }
    processor.kb_rag_storage.upload_embedding_with_retry.return_value = response


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

    def test_images_are_embedded_together_and_text_separately(self, processor):
        insights = [
            make_insight('d1', DocumentType.IMAGE, b'img-1'),
            make_insight('d2', DocumentType.TEXT, 'some text'),
            make_insight('d3', DocumentType.IMAGE, b'img-2'),
        ]

        assert processor.store(insights) is True

        processor.image_embedding.embed_images.assert_called_once_with(
            [b'img-1', b'img-2']
        )
        processor.kb_rag_storage.process_document.assert_called_once_with(['some text'])
        assert uploaded_doc_ids(processor) == ['d1', 'd2', 'd3']

    def test_text_only_batch_does_not_call_inference(self, processor):
        assert processor.store([make_insight('d1', DocumentType.TEXT, 'txt')]) is True

        processor.image_embedding.embed_images.assert_not_called()

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


class TestNoEmbeddingsAndRejections:
    def test_document_with_no_embeddings_is_failed_and_not_uploaded(self, processor):
        processor.kb_rag_storage.process_document.side_effect = lambda contents: (
            [] if contents == [''] else [EMBEDDING]
        )
        empty = make_insight('d1', DocumentType.TEXT, '')
        text = make_insight('d2', DocumentType.TEXT, 'some text')

        assert processor.store([empty, text]) is True

        assert uploaded_doc_ids(processor) == ['d2']
        assert empty.success is False
        assert 'no embeddings' in empty.error
        assert text.success is True

    def test_documents_rejected_by_floware_are_marked_failed(self, processor):
        set_floware_rejections(
            processor,
            {'D1': 'The embedding has a second vector but the KB only accepts one'},
        )
        image = make_insight('d1', DocumentType.IMAGE, b'img')
        text = make_insight('d2', DocumentType.TEXT, 'some text')

        assert processor.store([image, text]) is True

        assert image.success is False
        assert 'Rejected by floware' in image.error
        assert 'only accepts one' in image.error
        assert text.success is True


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


def published(processor) -> list:
    """(doc_id, status, error) for each status the processor published."""
    return [
        (c.args[0], c.args[2], c.kwargs.get('error'))
        for c in processor.index_status_publisher.publish.call_args_list
    ]


class TestIndexStatus:
    async def test_process_reports_in_progress(self, processor):
        processor.storage_manager.read_file.return_value = b'png-bytes'

        await processor.process(make_message('image/png', doc_id='doc-7'))

        processor.index_status_publisher.publish.assert_called_once_with(
            'doc-7', 'kb-1', IndexStatus.IN_PROGRESS, error=None
        )

    async def test_failed_process_result_carries_the_document(self, processor):
        processor.storage_manager.read_file.side_effect = Exception('bucket down')

        result = await processor.process(make_message('image/png', doc_id='doc-7'))

        assert result.success is False
        assert result.insights.doc_id == 'doc-7'
        assert result.insights.kb_id == 'kb-1'

    def test_store_reports_complete_only_for_stored_documents(self, processor):
        bad = make_insight('d1', DocumentType.IMAGE, b'bad')
        good = make_insight('d2', DocumentType.IMAGE, b'ok')

        assert processor.store([bad, good]) is True

        assert published(processor) == [('d2', IndexStatus.COMPLETE, None)]

    def test_failed_upload_reports_nothing(self, processor):
        processor.kb_rag_storage.upload_embedding_with_retry.side_effect = Exception(
            'floware down'
        )

        assert processor.store([make_insight('d1', DocumentType.TEXT, 'txt')]) is False

        assert published(processor) == []

    def test_complete_publish_failure_does_not_fail_the_store(self, processor):
        processor.index_status_publisher.publish.return_value = False

        assert processor.store([make_insight('d1', DocumentType.TEXT, 'txt')]) is True

    def test_is_failed_reports_failed_with_the_error(self, processor):
        failed = processor.failed_result(make_message('image/png', 'doc-9'), 'boom')

        assert processor.store([failed], is_failed=True) is True

        assert published(processor) == [('doc-9', IndexStatus.FAILED, 'boom')]
        processor.kb_rag_storage.upload_embedding_with_retry.assert_not_called()

    def test_is_failed_returns_false_when_failure_cannot_be_reported(self, processor):
        processor.index_status_publisher.publish.return_value = False
        failed = processor.failed_result(make_message('image/png', 'doc-9'), 'boom')

        assert processor.store([failed], is_failed=True) is False
