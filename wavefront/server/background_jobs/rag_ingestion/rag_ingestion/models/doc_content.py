from dataclasses import dataclass
from typing import Union
from rag_ingestion.processors.file_processor import DocumentType


@dataclass
class DocContent:
    """Model representing the extracted content from a document file"""

    content: Union[str, bytes]
    document_type: DocumentType
