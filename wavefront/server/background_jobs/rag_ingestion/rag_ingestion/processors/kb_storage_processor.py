from flo_cloud.cloud_storage import CloudStorageManager
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Optional, Tuple
from flo_utils.utils.log import logger
from common_module.runtime_settings import RuntimeSettings
from rag_ingestion.service.kb_rag_storage import KBRagStorage
from rag_ingestion.models.doc_content import DocContent
from rag_ingestion.stream.queue_message import QueueMessage
from flo_cloud.kms import FloKmsCipher
from flo_utils.streaming.message_processor import MessageProcessor, ProcessingResult
from rag_ingestion.processors.file_processor import FileProcessor, DocumentType
from rag_ingestion.embeddings.image_embed import ImageEmbedding
from rag_ingestion.models.knowledge_base_embeddings import KnowledgeBaseEmbeddingObject
from rag_ingestion.models.rag_message import RagEventMessage
from rag_ingestion.service.kb_rag_storage import EmbeddingsToStore
from rag_ingestion.service.index_status_publisher import IndexStatusPublisher
from db_repo_module.models.knowledge_base_documents import IndexStatus


@dataclass
class KbStorageInsights:
    doc_id: str
    # None on a failure result built before the content was extracted
    doc_content: Optional[DocContent]
    kb_id: str
    file_type: Optional[DocumentType]


class KbStorageProcessor(MessageProcessor):
    def __init__(
        self,
        storage_manager: CloudStorageManager,
        kms_cipher: FloKmsCipher | None,
        index_status_publisher: Optional[IndexStatusPublisher] = None,
        *,
        inference_service_url: str,
        runtime_settings: RuntimeSettings,
        text_embedding_batch_size: int | str = 16,
        image_embedding_batch_size: int | str = 8,
    ):
        self.storage_manager = storage_manager
        self.kms_cipher = kms_cipher
        self.index_status_publisher = index_status_publisher
        self.kb_rag_storage = KBRagStorage(
            inference_service_url=inference_service_url,
            runtime_settings=runtime_settings,
            text_embedding_batch_size=text_embedding_batch_size,
        )
        self.file_processor = FileProcessor()
        self.image_embedding = ImageEmbedding(
            inference_service_url=inference_service_url,
            batch_size=image_embedding_batch_size,
        )

    async def _extract_content(
        self, message: QueueMessage, file_content: bytes
    ) -> DocContent:
        """
        Extracts text content from a message based on its parse_type and file_type.

        Args:
            message: An object with 'parse_type' and 'file_type' attributes.
            file_content: The binary content of the file.

        Returns:
            A DocContent object with extracted content and parse_type.
        """
        (content, document_type) = self.file_processor.process_file(
            file_content, str(message.file_type)
        )
        return DocContent(content=content, document_type=document_type)

    def __embed_single_insight(
        self, kb_insight: ProcessingResult[KbStorageInsights]
    ) -> Tuple[List[KnowledgeBaseEmbeddingObject], str, str, DocumentType]:
        document_type = kb_insight.insights.doc_content.document_type
        if document_type in (DocumentType.PDF, DocumentType.TEXT):
            docs = self.kb_rag_storage.process_document(
                [kb_insight.insights.doc_content.content]
            )
        else:
            docs = []
        return (
            docs,
            kb_insight.insights.doc_id,
            kb_insight.insights.kb_id,
            document_type,
        )

    def __mark_embedding_failed(
        self,
        kb_insight: ProcessingResult[KbStorageInsights],
        err: Exception,
        failed_doc_ids: List[str],
    ):
        insight = kb_insight.insights
        kb_insight.success = False
        kb_insight.error = f'Embedding failed: {err}'
        failed_doc_ids.append(insight.doc_id)
        logger.error(
            f'Failed to embed doc {insight.doc_id} '
            f'(kb {insight.kb_id}, type {insight.file_type}): {err}',
            exc_info=err,
        )

    def __insert_kb_from_message(
        self, insights: List[ProcessingResult[KbStorageInsights]]
    ):
        """
        Embeds each document in the batch and uploads the embeddings in one request.

        Text and PDF documents are embedded in parallel; images are sent to the
        inference service together in batches. A document that fails to embed
        (e.g. an image the inference service rejects) is marked failed on its
        ProcessingResult and left out of the upload, so the listener retries
        just that message. Upload failures are raised so store() fails the
        whole batch.

        Args:
            insights: Processing results holding each document's extracted content.

        Returns:
            None
        """
        logger.info('Embeddings storing process is started')
        embeddings: List[EmbeddingsToStore] = []
        failed_doc_ids: List[str] = []
        image_insights = [
            kb_insight
            for kb_insight in insights
            if kb_insight.insights.doc_content.document_type == DocumentType.IMAGE
        ]
        other_insights = [
            kb_insight
            for kb_insight in insights
            if kb_insight.insights.doc_content.document_type != DocumentType.IMAGE
        ]
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(self.__embed_single_insight, kb_insight): kb_insight
                for kb_insight in other_insights
            }

            # Runs while the text/PDF futures are in flight.
            image_results = (
                self.image_embedding.embed_images(
                    [ki.insights.doc_content.content for ki in image_insights]
                )
                if image_insights
                else []
            )
            for kb_insight, result in zip(image_insights, image_results):
                if result.error is not None:
                    self.__mark_embedding_failed(
                        kb_insight, result.error, failed_doc_ids
                    )
                    continue
                embeddings.append(
                    EmbeddingsToStore(
                        kb_embeddings=[result.embedding],
                        doc_id=kb_insight.insights.doc_id,
                        kb_id=kb_insight.insights.kb_id,
                        file_type=DocumentType.IMAGE,
                    )
                )

            for future in as_completed(futures):
                kb_insight = futures[future]
                try:
                    docs, doc_id, kb_id, document_type = future.result()
                except Exception as err:
                    self.__mark_embedding_failed(kb_insight, err, failed_doc_ids)
                    continue
                if not docs:
                    # e.g. an empty file or a scanned PDF with no text layer;
                    # floware would reject it, so don't send it at all
                    self.__mark_embedding_failed(
                        kb_insight,
                        ValueError('The document produced no embeddings'),
                        failed_doc_ids,
                    )
                    continue
                embeddings.append(
                    EmbeddingsToStore(
                        kb_embeddings=docs,
                        doc_id=doc_id,
                        kb_id=kb_id,
                        file_type=document_type,
                    )
                )

        if not embeddings:
            logger.error(
                f'Embedding failed for every document in the batch: {failed_doc_ids}'
            )
            return

        response = self.kb_rag_storage.upload_embedding_with_retry(
            embeddings=embeddings
        )
        rejected_doc_ids = self.__mark_rejected_by_floware(insights, response)
        logger.info(
            f'Stored embeddings for {len(embeddings) - len(rejected_doc_ids)} doc(s); '
            f'{len(failed_doc_ids)} failed to embed: {failed_doc_ids}; '
            f'{len(rejected_doc_ids)} rejected by floware: {rejected_doc_ids}'
        )

    def __mark_rejected_by_floware(
        self, insights: List[ProcessingResult[KbStorageInsights]], response
    ) -> List[str]:
        """Mark documents floware left out of the upload as failed.

        floware stores valid documents and lists the rest under
        `data.rejected` (e.g. an image sent to a text knowledge base).
        """
        rejected = (response.json().get('data') or {}).get('rejected') or []
        reasons = {
            str(item['document_id']).lower(): item.get('reason', 'rejected')
            for item in rejected
        }
        rejected_doc_ids = []
        for kb_insight in insights:
            doc_id = str(kb_insight.insights.doc_id).lower()
            if kb_insight.success and doc_id in reasons:
                kb_insight.success = False
                kb_insight.error = f'Rejected by floware: {reasons[doc_id]}'
                rejected_doc_ids.append(kb_insight.insights.doc_id)
                logger.error(
                    f'floware rejected doc {kb_insight.insights.doc_id} '
                    f'(kb {kb_insight.insights.kb_id}): {reasons[doc_id]}',
                    exc_info=False,
                )
        return rejected_doc_ids

    async def process(
        self, message: RagEventMessage
    ) -> ProcessingResult[KbStorageInsights]:
        """
        Main public interface for processing messages and generating embeddings.

        Args:
            message: Queue message containing document information

        Returns:
            ProcessingResult indicating success/failure and any insights
        """
        logger.info(f'Processing message: {message.id}')
        logger.info(f'Processing file: {message.bucket_name}/{message.bucket_key}')
        # Best effort: indexing goes ahead even if floware can't be told.
        self.__publish_status(message.doc_id, message.kb_id, IndexStatus.IN_PROGRESS)

        # An exception escaping process() makes the stream listener abandon every
        # message it received alongside this one, so fail only this message.
        try:
            file_content_encrypt = self.storage_manager.read_file(
                message.bucket_name, message.bucket_key
            )
            file_content = (
                self.kms_cipher.decrypt(file_content_encrypt)
                if self.kms_cipher
                else file_content_encrypt
            )
            doc_content = await self._extract_content(message, file_content)
        except Exception as err:
            logger.error(
                f'Failed to extract content for doc {message.doc_id} '
                f'({message.file_type}): {err}',
                exc_info=True,
            )
            return self.failed_result(message, str(err))
        return ProcessingResult[KbStorageInsights](
            success=True,
            insights=KbStorageInsights(
                doc_id=message.doc_id,
                doc_content=doc_content,
                kb_id=message.kb_id,
                file_type=doc_content.document_type,
            ),
        )

    def failed_result(
        self, message: RagEventMessage, error: str
    ) -> ProcessingResult[KbStorageInsights]:
        """A failed result carrying the message's doc and KB ids, so the
        failure can be reported for that document."""
        return ProcessingResult[KbStorageInsights](
            success=False,
            error=error,
            insights=KbStorageInsights(
                doc_id=message.doc_id,
                doc_content=None,
                kb_id=message.kb_id,
                file_type=None,
            ),
        )

    def store(
        self,
        insights: List[ProcessingResult[KbStorageInsights]],
        is_failed: bool = False,
    ) -> bool:
        if not insights:
            return False
        if is_failed:
            return self.__record_failures(insights)
        try:
            self.__insert_kb_from_message(insights)
        except Exception as e:
            logger.error(f'Failed to store data to the database: {e}')
            return False
        for kb_insight in insights:
            if kb_insight.success:
                # Embeddings are stored; if this event is lost the document
                # shows IN_PROGRESS, but retrying would duplicate embeddings,
                # so it is logged rather than failing the message.
                self.__publish_status(
                    kb_insight.insights.doc_id,
                    kb_insight.insights.kb_id,
                    IndexStatus.COMPLETE,
                )
        return True

    def __record_failures(
        self, insights: List[ProcessingResult[KbStorageInsights]]
    ) -> bool:
        """Report FAILED for documents the listener has given up on. Returns
        True only if every failure reached floware, so the listener keeps the
        messages queued otherwise."""
        recorded = True
        for kb_insight in insights:
            insight = kb_insight.insights
            if insight is None:
                continue
            published = self.__publish_status(
                insight.doc_id,
                insight.kb_id,
                IndexStatus.FAILED,
                error=kb_insight.error or 'Indexing failed',
            )
            recorded = recorded and published
        return recorded

    def __publish_status(
        self,
        doc_id: str,
        kb_id: Optional[str],
        status: IndexStatus,
        error: Optional[str] = None,
    ) -> bool:
        if self.index_status_publisher is None:
            return True
        return self.index_status_publisher.publish(doc_id, kb_id, status, error=error)
