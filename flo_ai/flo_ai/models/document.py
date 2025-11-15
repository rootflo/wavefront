"""
Document-related data models for Flo AI framework.

This module contains document types and message classes to avoid circular imports.
"""

from enum import Enum


class DocumentType(Enum):
    """Enumeration of supported document types."""

    PDF = 'application/pdf'
    TXT = 'text/plain'
