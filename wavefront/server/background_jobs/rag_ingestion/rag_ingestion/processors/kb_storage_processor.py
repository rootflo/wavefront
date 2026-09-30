from flo_cloud.cloud_storage import CloudStorageManager
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Tuple
from flo_utils.utils.log import logger
from rag_ingestion.service.kb_rag_storage import KBRagStorage
from rag_ingestion.embeddings.embed import EmbeddingFunc
from rag_ingestion.models.doc_content import DocContent
from rag_ingestion.stream.queue_message import QueueMessage
from flo_cloud.kms import FloKmsService
from flo_utils.streaming.message_processor import MessageProcessor, ProcessingResult
from rag_ingestion.processors.file_processor import FileProcessor, DocumentType
from rag_ingestion.embeddings.image_embed import ImageEmbedding
from rag_ingestion.models.knowledge_base_embeddings import KnowledgeBaseEmbeddingObject
from rag_ingestion.models.rag_message import RagEventMessage
from rag_ingestion.service.kb_rag_storage import EmbeddingsToStore


@dataclass
class KbStorageInsights:
    doc_id: str
    doc_content: DocContent
    kb_id: str
    file_type: DocumentType


class KbStorageProcessor(MessageProcessor):
    def __init__(
        self,
        storage_manager: CloudStorageManager,
        encryption_service: FloKmsService,
    ):
        self.storage_manager = storage_manager
        self.encryption_service = encryption_service
        self.kb_rag_storage = KBRagStorage()
        self.embedding_func = EmbeddingFunc()
        self.file_processor = FileProcessor()
        self.image_embedding = ImageEmbedding()

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

        self.kb_rag_storage.upload_embedding_with_retry(embeddings=embeddings)
        logger.info(
            f'Stored embeddings for {len(embeddings)} doc(s); '
            f'{len(failed_doc_ids)} failed to embed: {failed_doc_ids}'
        )

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

        # An exception escaping process() makes the stream listener abandon every
        # message it received alongside this one, so fail only this message.
        try:
            file_content_encrypt = self.storage_manager.read_file(
                message.bucket_name, message.bucket_key
            )
            file_content = (
                self.encryption_service.decrypt(file_content_encrypt)
                if self.encryption_service
                else file_content_encrypt
            )
            doc_content = await self._extract_content(message, file_content)
        except Exception as err:
            logger.error(
                f'Failed to extract content for doc {message.doc_id} '
                f'({message.file_type}): {err}',
                exc_info=True,
            )
            return ProcessingResult[KbStorageInsights](success=False, error=str(err))
        return ProcessingResult[KbStorageInsights](
            success=True,
            insights=KbStorageInsights(
                doc_id=message.doc_id,
                doc_content=doc_content,
                kb_id=message.kb_id,
                file_type=doc_content.document_type,
            ),
        )

    def store(self, insights: List[ProcessingResult[KbStorageInsights]]):
        if not insights:
            return False
        try:
            self.__insert_kb_from_message(insights)
            return True
        except Exception as e:
            logger.error(f'Failed to store data to the database: {e}')
            return False
