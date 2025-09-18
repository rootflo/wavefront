"""
Document-related data models for Flo AI framework.

This module contains document types and message classes to avoid circular imports.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional


class DocumentType(Enum):
    """Enumeration of supported document types."""

    PDF = 'pdf'
    TXT = 'txt'


@dataclass
class DocumentMessage:
    """
    Data structure for document inputs to LLMs.

    Supports various document formats with extensible design for future types.
    """

    document_type: DocumentType
    document_url: Optional[str] = None
    document_bytes: Optional[bytes] = None
    document_file_path: Optional[str] = None
    document_base64: Optional[str] = None
    mime_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
