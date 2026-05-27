"""
Document processing utilities for Flo AI framework.

This module exposes lightweight helpers used by LLM adapters that need to
produce a text representation of a document (e.g. the plain Ollama adapter)
or an image rasterization of a PDF (e.g. vision chat models that do not
accept PDFs natively).
"""

import base64
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Union

import pymupdf
import chardet

from flo_ai.models.document import DocumentType
from flo_ai.models.chat_message import DocumentMessageContent
from flo_ai.utils.logger import logger


class DocumentProcessingError(Exception):
    """Exception raised when document processing fails."""

    pass


class BaseDocumentProcessor(ABC):
    """Abstract base class for document processors."""

    @abstractmethod
    async def process(self, document: DocumentMessageContent) -> Dict[str, Any]:
        """Process a document and return extracted content and metadata."""
        pass


class PDFProcessor(BaseDocumentProcessor):
    """Processor for PDF documents using PyMuPDF's text layer.

    Intentionally avoids pymupdf4llm / markdown conversion / table detection:
    modern LLMs perform that structuring far better than a local heuristic,
    and the raw text layer is 10-50x cheaper to produce.
    """

    async def process(self, document: DocumentMessageContent) -> Dict[str, Any]:
        try:
            pdf_content = await self._get_pdf_content(document)
            text_data = self._extract_with_pymupdf(pdf_content)
            return {
                'extracted_text': text_data['text'],
                'page_count': text_data.get('page_count', 0),
                'processing_method': text_data.get('method', 'pymupdf'),
                'metadata': text_data.get('metadata', {}),
                'document_type': DocumentType.PDF.value,
            }
        except Exception as e:
            logger.error(f'Error processing PDF: {str(e)}')
            raise DocumentProcessingError(f'Failed to process PDF: {str(e)}')

    async def _get_pdf_content(
        self, document: DocumentMessageContent
    ) -> Union[str, bytes]:
        if document.bytes:
            return document.bytes
        if document.base64:
            return base64.b64decode(document.base64)
        if document.url:
            return document.url
        raise DocumentProcessingError('No PDF content provided')

    @staticmethod
    def _extract_with_pymupdf(pdf_content: Union[str, bytes]) -> Dict[str, Any]:
        """Extract plain text using PyMuPDF. No markdown, no table OCR."""
        if isinstance(pdf_content, str):
            doc = pymupdf.open(pdf_content)
        else:
            doc = pymupdf.open(stream=pdf_content, filetype='pdf')
        try:
            pages = [page.get_text() for page in doc]
        finally:
            doc.close()

        return {
            'text': '\n\n---\n\n'.join(pages),
            'method': 'pymupdf',
            'metadata': {},
            'page_count': len(pages),
        }


class TXTProcessor(BaseDocumentProcessor):
    """Processor for text documents."""

    async def process(self, document: DocumentMessageContent) -> Dict[str, Any]:
        try:
            text_content = await self._get_text_content(document)
            return {
                'extracted_text': text_content,
                'page_count': 1,
                'processing_method': 'text_reader',
                'metadata': {
                    'character_count': len(text_content),
                    'line_count': len(text_content.splitlines()),
                    'encoding': 'utf-8',
                },
                'document_type': DocumentType.TXT.value,
            }
        except Exception as e:
            logger.error(f'Error processing TXT: {str(e)}')
            raise DocumentProcessingError(f'Failed to process TXT: {str(e)}')

    async def _get_text_content(self, document: DocumentMessageContent) -> str:
        if document.bytes:
            return await self._decode_bytes(document.bytes)
        if document.base64:
            return await self._decode_bytes(base64.b64decode(document.base64))
        raise DocumentProcessingError('No TXT content provided')

    async def _decode_bytes(self, content_bytes: bytes) -> str:
        try:
            return content_bytes.decode('utf-8')
        except UnicodeDecodeError:
            detected = chardet.detect(content_bytes)
            encoding = detected.get('encoding', 'utf-8')
            return content_bytes.decode(encoding, errors='replace')


class DocumentProcessor:
    """Factory / dispatcher for :class:`BaseDocumentProcessor` implementations."""

    def __init__(self) -> None:
        self._processors: Dict[DocumentType, BaseDocumentProcessor] = {
            DocumentType.PDF: PDFProcessor(),
            DocumentType.TXT: TXTProcessor(),
        }

    def register_processor(
        self, document_type: DocumentType, processor: BaseDocumentProcessor
    ) -> None:
        """Register a processor for an additional document type."""
        self._processors[document_type] = processor

    async def process_document(
        self, document: DocumentMessageContent
    ) -> Dict[str, Any]:
        if not document.mime_type:
            raise DocumentProcessingError('Document mime_type is required')

        document_type = None
        for doc_type in DocumentType:
            if doc_type.value == document.mime_type:
                document_type = doc_type
                break

        if document_type is None or document_type not in self._processors:
            raise DocumentProcessingError(
                f'Unsupported document type: {document.mime_type}. '
                f'Supported types: {[dt.value for dt in self._processors.keys()]}'
            )

        processor = self._processors[document_type]
        try:
            result = await processor.process(document)
            result['processing_timestamp'] = time.time()
            logger.info(
                f"Successfully processed {document_type.value} document "
                f"using {result.get('processing_method', 'unknown')} method"
            )
            return result
        except Exception as e:
            logger.error(f'Document processing failed: {str(e)}')
            raise


_default_processor: 'DocumentProcessor | None' = None


def get_default_processor() -> DocumentProcessor:
    """Get the default DocumentProcessor instance (lazy singleton)."""
    global _default_processor
    if _default_processor is None:
        _default_processor = DocumentProcessor()
    return _default_processor
