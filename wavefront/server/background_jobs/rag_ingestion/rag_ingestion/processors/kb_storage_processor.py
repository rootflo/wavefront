from flo_cloud.cloud_storage import CloudStorageManager
from dataclasses import dataclass
from typing import List
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

    def __insert_kb_from_message(
        self, insights: List[ProcessingResult[KbStorageInsights]]
    ):
        """
        Processes a message transcript and inserts KB embeddings if the conversation type is 'kb_insertion'.

        Args:
            message: An object with a 'doc_id' field.
            doc_content: A DocContent object containing the extracted text.

        Returns:
            None
        """
        try:
            embeddings: List[EmbeddingsToStore] = []
            for kb_insight in insights:
                kb_id = kb_insight.insights.kb_id
                doc_id = kb_insight.insights.doc_id
                document_type = kb_insight.insights.doc_content.document_type

                logger.info('Embeddings storing process is started')
                if (
                    document_type == DocumentType.PDF
                    or document_type == DocumentType.TEXT
                ):
                    extracted_docs = [kb_insight.insights.doc_content.content]
                    docs: List[KnowledgeBaseEmbeddingObject] = (
                        self.kb_rag_storage.process_document(extracted_docs)
                    )
                elif document_type == DocumentType.IMAGE:
                    image_data = [kb_insight.insights.doc_content.content]
                    docs: List[KnowledgeBaseEmbeddingObject] = [
                        self.image_embedding.embed_image(image_data)
                        for image_data in image_data
                    ]
                embeddings.append(
                    EmbeddingsToStore(
                        kb_embeddings=docs,
                        doc_id=doc_id,
                        kb_id=kb_id,
                        file_type=document_type,
                    )
                )

            self.kb_rag_storage.upload_embedding_with_retry(embeddings=embeddings)
            logger.info('Embeddings are stored in the db')
        except Exception as err:
            logger.info(f'The error message captured is {err}')

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

        file_content_encrypt = self.storage_manager.read_file(
            message.bucket_name, message.bucket_key
        )
        file_content = (
            self.encryption_service.decrypt(file_content_encrypt)
            if self.encryption_service
            else file_content_encrypt
        )
        doc_content = await self._extract_content(message, file_content)
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
