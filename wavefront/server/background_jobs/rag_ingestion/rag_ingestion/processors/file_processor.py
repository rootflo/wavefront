import os
import tempfile
import textract
from typing import Tuple
from enum import Enum
from common_module.log.logger import logger


class DocumentType(Enum):
    PDF = 'pdf'
    IMAGE = 'image'
    TEXT = 'text'


class FileProcessor:
    def process_file(
        self, file_content: bytes, file_type: str
    ) -> Tuple[str | bytes, DocumentType]:
        mime_type = file_type
        document_type = self.extract_document_type(mime_type)
        if document_type == DocumentType.TEXT:
            return file_content.decode('utf-8'), DocumentType.TEXT

        if document_type == DocumentType.IMAGE:
            return file_content, DocumentType.IMAGE

        if document_type == DocumentType.PDF:
            with tempfile.NamedTemporaryFile(
                mode='w+b', delete=False, suffix='.pdf'
            ) as temp_file:
                temp_file.write(file_content)
                temp_file.flush()
                temp_file_path = temp_file.name

            try:
                text_content = textract.process(
                    temp_file_path, method='pdfminer'
                ).decode('utf-8')
                return text_content, DocumentType.PDF

            except Exception as e:
                logger.error(f'Text extraction failed for {mime_type}: {e}')
                raise RuntimeError(f'Text extraction failed for {mime_type}: {e}')

            finally:
                os.unlink(temp_file_path)

        # Explicit raise to prevent implicit None return.
        raise RuntimeError(f'Unsupported or unknown document type: {document_type}')

    def extract_document_type(self, file_type: str) -> DocumentType:
        if file_type.startswith('text/plain'):
            return DocumentType.TEXT
        if file_type.startswith('image/'):
            return DocumentType.IMAGE
        if file_type in ('application/pdf', 'application/x-pdf'):
            return DocumentType.PDF
        else:
            raise ValueError(f'Unsupported file type: {file_type}')
