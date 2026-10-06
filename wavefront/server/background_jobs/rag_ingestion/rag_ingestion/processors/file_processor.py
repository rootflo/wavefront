import codecs
import os
import tempfile
import charset_normalizer
import textract
from typing import Optional, Tuple
from enum import Enum
from common_module.log.logger import logger
from common_module.utils.image_formats import SUPPORTED_PILLOW_MIME_TYPES


# When several encodings fit a single-byte file equally well (common for
# Western European text: cp1250, cp1252 and latin-1 agree on most bytes),
# prefer the most widely used. cp1252 decodes latin-1 text identically for
# every printable character.
_PREFERRED_ON_TIE = ('cp1252', 'iso8859_15', 'latin_1')


def decode_text(content: bytes, declared_charset: Optional[str] = None) -> str:
    """Decode an uploaded text file whatever its encoding.

    In order:
    1. The charset the upload declared (e.g. `text/plain; charset=...`), if
       Python knows it and it decodes the bytes cleanly.
    2. UTF-8, with or without a BOM: the common case, and decoding is exact.
    3. Detection with charset-normalizer (UTF-16, Windows-1252, Shift-JIS,
       ...), breaking ties between equally good single-byte candidates in
       favour of _PREFERRED_ON_TIE.
    4. UTF-8 with invalid sequences replaced by U+FFFD, so the document is
       still indexed rather than failing.
    """
    if declared_charset:
        try:
            if codecs.lookup(declared_charset).name == 'utf-8':
                declared_charset = 'utf-8-sig'
            return content.decode(declared_charset)
        except (LookupError, UnicodeDecodeError) as err:
            logger.warning(
                f'Declared charset {declared_charset!r} did not decode the '
                f'file ({err}); detecting the encoding instead'
            )
    try:
        return content.decode('utf-8-sig')
    except UnicodeDecodeError:
        pass
    matches = charset_normalizer.from_bytes(content)
    best = matches.best()
    if best is not None:
        tied = {
            match.encoding: match
            for match in matches
            if match.chaos == best.chaos and match.coherence == best.coherence
        }
        best = next((tied[name] for name in _PREFERRED_ON_TIE if name in tied), best)
        logger.info(f'Decoded text file as {best.encoding}')
        return str(best)
    logger.warning(
        'Could not detect the text encoding; decoding as UTF-8 with '
        'invalid bytes replaced'
    )
    return content.decode('utf-8', errors='replace')


def _declared_charset(file_type: str) -> Optional[str]:
    """The charset parameter of a MIME type, e.g. 'text/plain; charset=utf-16'."""
    for param in file_type.split(';')[1:]:
        name, _, value = param.partition('=')
        if name.strip().lower() == 'charset' and value.strip():
            return value.strip().strip('"\'')
    return None


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
            return (
                decode_text(file_content, _declared_charset(file_type)),
                DocumentType.TEXT,
            )

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
            # The inference service only decodes SUPPORTED_PILLOW_FORMATS; fail
            # here rather than after a round trip to it.
            mime_type = file_type.split(';')[0].strip().lower()
            if mime_type not in SUPPORTED_PILLOW_MIME_TYPES:
                raise ValueError(f'Unsupported image type: {file_type}')
            return DocumentType.IMAGE
        if file_type in ('application/pdf', 'application/x-pdf'):
            return DocumentType.PDF
        else:
            raise ValueError(f'Unsupported file type: {file_type}')
