"""
Document processing utilities for Flo AI framework.

This module provides extensible document processing capabilities for PDF and TXT files,
with a factory pattern design for easy addition of new document types.
"""

import os
import base64
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Union

import pymupdf
import pymupdf4llm
import chardet

from flo_ai.models.document import DocumentMessage, DocumentType
from flo_ai.utils.logger import logger


class DocumentProcessingError(Exception):
    """Exception raised when document processing fails."""

    pass


class BaseDocumentProcessor(ABC):
    """Abstract base class for document processors."""

    @abstractmethod
    async def process(self, document: DocumentMessage) -> Dict[str, Any]:
        """
        Process a document and return extracted content and metadata.

        Args:
            document: DocumentMessage containing document data

        Returns:
            Dict containing extracted text, metadata, and processing info
        """
        pass


class PDFProcessor(BaseDocumentProcessor):
    """Processor for PDF documents."""

    async def process(self, document: DocumentMessage) -> Dict[str, Any]:
        """Extract text and metadata from PDF document."""
        try:
            pdf_content = await self._get_pdf_content(document)

            # Process with pymupdf4llm (LLM-optimized)
            text_data = await self._process_with_pymupdf4llm(pdf_content)

            return {
                'extracted_text': text_data['text'],
                'page_count': text_data.get('page_count', 0),
                'processing_method': text_data.get('method', 'unknown'),
                'metadata': text_data.get('metadata', {}),
                'document_type': DocumentType.PDF.value,
            }

        except Exception as e:
            logger.error(f'Error processing PDF: {str(e)}')
            raise DocumentProcessingError(f'Failed to process PDF: {str(e)}')

    async def _get_pdf_content(self, document: DocumentMessage) -> Union[str, bytes]:
        """Get PDF content from various sources."""
        if document.document_file_path:
            if not os.path.exists(document.document_file_path):
                raise DocumentProcessingError(
                    f'PDF file not found: {document.document_file_path}'
                )
            return document.document_file_path
        elif document.document_bytes:
            return document.document_bytes
        elif document.document_base64:
            return base64.b64decode(document.document_base64)
        else:
            raise DocumentProcessingError('No PDF content provided')

    async def _process_with_pymupdf4llm(
        self, pdf_content: Union[str, bytes]
    ) -> Dict[str, Any]:
        """Process PDF using pymupdf4llm (LLM-optimized)."""
        if isinstance(pdf_content, str):
            # File path - pass directly to pymupdf4llm
            text_data = pymupdf4llm.to_markdown(pdf_content)
            metadata = {}
        else:
            # Bytes - create PyMuPDF Document from memory
            doc = pymupdf.open(stream=pdf_content)
            try:
                text_data = pymupdf4llm.to_markdown(doc)
                metadata = {}
            finally:
                doc.close()  # Clean up document object

        return {
            'text': text_data,
            'method': 'pymupdf4llm',
            'metadata': metadata,
            'page_count': len(text_data.split('\n---\n')) if '---' in text_data else 1,
        }


class TXTProcessor(BaseDocumentProcessor):
    """Processor for text documents."""

    async def process(self, document: DocumentMessage) -> Dict[str, Any]:
        """Extract text from TXT document."""
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

    async def _get_text_content(self, document: DocumentMessage) -> str:
        """Get text content from various sources."""
        if document.document_file_path:
            if not os.path.exists(document.document_file_path):
                raise DocumentProcessingError(
                    f'TXT file not found: {document.document_file_path}'
                )
            return await self._read_text_file(document.document_file_path)
        elif document.document_bytes:
            return await self._decode_bytes(document.document_bytes)
        elif document.document_base64:
            decoded_bytes = base64.b64decode(document.document_base64)
            return await self._decode_bytes(decoded_bytes)
        else:
            raise DocumentProcessingError('No TXT content provided')

    async def _read_text_file(self, file_path: str) -> str:
        """Read text file with encoding detection."""
        try:
            # Try UTF-8 first
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            # Try encoding detection with chardet
            with open(file_path, 'rb') as f:
                raw_data = f.read()
            detected = chardet.detect(raw_data)
            encoding = detected.get('encoding', 'utf-8')
            return raw_data.decode(encoding, errors='replace')

    async def _decode_bytes(self, content_bytes: bytes) -> str:
        """Decode bytes with encoding detection."""
        try:
            return content_bytes.decode('utf-8')
        except UnicodeDecodeError:
            detected = chardet.detect(content_bytes)
            encoding = detected.get('encoding', 'utf-8')
            return content_bytes.decode(encoding, errors='replace')


class DocumentProcessor:
    """
    Main document processor with factory pattern for extensibility.

    Supports PDF and TXT documents with easy extension for new types.
    """

    def __init__(self):
        self._processors = {
            DocumentType.PDF: PDFProcessor(),
            DocumentType.TXT: TXTProcessor(),
        }

    def register_processor(
        self, document_type: DocumentType, processor: BaseDocumentProcessor
    ):
        """Register a new document processor for a specific type."""
        self._processors[document_type] = processor

    async def process_document(self, document: DocumentMessage) -> Dict[str, Any]:
        """
        Process a document using the appropriate processor.

        Args:
            document: DocumentMessage containing document data

        Returns:
            Dict containing extracted content and metadata

        Raises:
            DocumentProcessingError: If processing fails or document type unsupported
        """
        if document.document_type not in self._processors:
            raise DocumentProcessingError(
                f'Unsupported document type: {document.document_type}. '
                f'Supported types: {list(self._processors.keys())}'
            )

        processor: BaseDocumentProcessor = self._processors[document.document_type]

        try:
            result = await processor.process(document)

            # Add common metadata
            result['processing_timestamp'] = time.time()

            logger.info(
                f"Successfully processed {document.document_type.value} document "
                f"using {result.get('processing_method', 'unknown')} method"
            )

            return result

        except Exception as e:
            logger.error(f'Document processing failed: {str(e)}')
            raise


# Lazy singleton for default processor
_default_processor = None


def get_default_processor() -> DocumentProcessor:
    """Get the default DocumentProcessor instance (lazy singleton)."""
    global _default_processor
    if _default_processor is None:
        _default_processor = DocumentProcessor()
    return _default_processor
