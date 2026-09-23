"""Text extraction for Office and plain-text documents.

Documents normally reach the provider as a flo_ai ``DocumentMessageContent``,
which each adapter either rasterizes (OpenAI/Azure, via PyMuPDF) or forwards as
a native document block (Anthropic, Gemini). None of those paths accept Word or
Excel: the Chat Completions API this deployment targets takes PDF only, and
Anthropic's document block takes PDF and plain text. Bedrock's Converse API does
accept Office formats natively, but it is not the provider this deployment
targets.

So Office and CSV files are converted to text here, at the API boundary, and
enter the conversation as an ordinary ``TextMessageContent``. flo_ai stays
unchanged -- it deliberately ships no text-extraction fallback, see the
docstring on ``BaseLLM.format_document_in_message`` -- and the formats then work
identically on every provider, including ones with no document support at all.

A note on trust: the mime type reaching this module comes from the client, and
here it selects which parser runs. That is the same hazard
``common_module.utils.image_formats`` documents for Pillow decoders, so every
handler that needs a specific container verifies its magic bytes first rather
than trusting the declared type.
"""

import csv
import io
import os
import subprocess
import tempfile
import zipfile
from typing import Callable, Dict, List, Optional

from common_module.log.logger import logger

TEXT_MIME_TYPE = 'text/plain'
CSV_MIME_TYPE = 'text/csv'
DOC_MIME_TYPE = 'application/msword'
DOCX_MIME_TYPE = (
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
)
XLS_MIME_TYPE = 'application/vnd.ms-excel'
XLSX_MIME_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

#: Document mime types that are converted to text rather than sent to the
#: provider as a document block. ``application/pdf`` is deliberately absent: it
#: keeps its existing native/rasterized path.
EXTRACTABLE_DOCUMENT_MIME_TYPES = frozenset(
    {
        TEXT_MIME_TYPE,
        CSV_MIME_TYPE,
        DOC_MIME_TYPE,
        DOCX_MIME_TYPE,
        XLS_MIME_TYPE,
        XLSX_MIME_TYPE,
    }
)

# OOXML (.docx/.xlsx) files are ZIP containers; the legacy binary formats
# (.doc/.xls) are OLE2 compound files.
_ZIP_MAGIC = b'PK\x03\x04'
_OLE2_MAGIC = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'


def _env_int(name: str, default: int) -> int:
    """Read a positive int from the environment, falling back on anything odd."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning(f'{name}={raw!r} is not an integer; using {default}')
        return default
    if value <= 0:
        logger.warning(f'{name}={value} must be positive; using {default}')
        return default
    return value


#: Characters of extracted text handed to the model per document. Roughly 50k
#: tokens -- large enough for a normal report, small enough that one oversized
#: spreadsheet cannot consume a whole context window.
MAX_EXTRACTED_CHARS = _env_int('DOCUMENT_MAX_EXTRACTED_CHARS', 200_000)

#: Upper bound on the raw upload we will attempt to parse. Matches the limit the
#: web client already enforces on document uploads.
MAX_DOCUMENT_BYTES = _env_int('DOCUMENT_MAX_BYTES', 50 * 1024 * 1024)

#: Bounds on what an OOXML container may expand to. A few hundred kB of ZIP can
#: otherwise inflate to gigabytes inside a worker.
MAX_UNCOMPRESSED_BYTES = _env_int('DOCUMENT_MAX_UNCOMPRESSED_BYTES', 400 * 1024 * 1024)
MAX_COMPRESSION_RATIO = _env_int('DOCUMENT_MAX_COMPRESSION_RATIO', 200)

#: antiword is a small C program from 2005. Bound how long it may run.
ANTIWORD_TIMEOUT_SECONDS = _env_int('DOCUMENT_ANTIWORD_TIMEOUT_SECONDS', 30)


class DocumentExtractionError(Exception):
    """Raised when a document cannot be converted to text.

    Callers at the API boundary turn this into a 400. The message is safe to
    return to the caller: it never contains document content.
    """


def _decode_text(data: bytes) -> str:
    """Decode bytes that are meant to be text, tolerating common encodings.

    ``utf-8-sig`` first because spreadsheets exported from Excel carry a BOM,
    then cp1252 as the usual source of stray bytes in Windows-authored CSVs.
    Latin-1 last: it cannot fail, so there is always a result rather than a 400
    on a single bad byte.
    """
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode('latin-1', errors='replace')


def _require_magic(data: bytes, magic: bytes, expected: str) -> None:
    """Reject content whose leading bytes do not match the expected container."""
    if not data.startswith(magic):
        raise DocumentExtractionError(
            f'File content does not look like a {expected} file. '
            f'The file may be corrupt, or its extension may not match '
            f'its actual format.'
        )


def _guard_zip_bomb(data: bytes) -> None:
    """Reject OOXML containers that expand far beyond their compressed size.

    Reads only the central directory, so this costs nothing on a normal file and
    runs before any parser touches the archive.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            total = sum(info.file_size for info in archive.infolist())
    except zipfile.BadZipFile as exc:
        raise DocumentExtractionError(f'File is not a readable archive: {exc}') from exc

    if total > MAX_UNCOMPRESSED_BYTES:
        raise DocumentExtractionError(
            f'File expands to {total} bytes, over the '
            f'{MAX_UNCOMPRESSED_BYTES} byte limit.'
        )
    if data and total / len(data) > MAX_COMPRESSION_RATIO:
        raise DocumentExtractionError(
            f'File has a compression ratio above {MAX_COMPRESSION_RATIO}:1, '
            f'which is characteristic of a decompression bomb.'
        )


def _rows_to_text(rows: List[List[str]]) -> str:
    """Render rows as CSV.

    CSV rather than a markdown table: models read it just as well and it costs a
    fraction of the tokens on a wide sheet. Uses the csv writer so that values
    containing commas or newlines stay unambiguous.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().strip('\n')


def _cell_to_str(value: object) -> str:
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        # openpyxl and xlrd both return every number as a float; without this
        # every integer in the sheet reaches the model as "1.0".
        return str(int(value))
    return str(value)


def _trim_trailing_empty(rows: List[List[str]]) -> List[List[str]]:
    """Drop trailing empty cells per row, and trailing empty rows.

    Spreadsheet readers report the full used range, which is routinely padded
    with hundreds of empty cells from stray formatting.
    """
    trimmed: List[List[str]] = []
    for row in rows:
        while row and not row[-1].strip():
            row.pop()
        trimmed.append(row)
    while trimmed and not any(cell.strip() for cell in trimmed[-1]):
        trimmed.pop()
    return trimmed


def _extract_plain_text(data: bytes) -> str:
    return _decode_text(data)


def _extract_csv(data: bytes) -> str:
    # Already delimited text. Decode and pass through rather than re-serializing:
    # round-tripping through the csv module would normalize the author's
    # delimiter and quoting for no benefit.
    return _decode_text(data)


def _extract_docx(data: bytes) -> str:
    _require_magic(data, _ZIP_MAGIC, 'Word (.docx)')
    _guard_zip_bomb(data)

    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(io.BytesIO(data))

    # Walk the body in document order rather than `document.paragraphs` then
    # `document.tables`: in a typical report the tables carry most of the
    # content, and reading them all after the prose loses which section each
    # belonged to.
    parts: List[str] = []
    for element in document.element.body.iterchildren():
        tag = element.tag
        if tag.endswith('}p'):
            text = Paragraph(element, document).text.strip()
            if text:
                parts.append(text)
        elif tag.endswith('}tbl'):
            rows = [
                [cell.text.strip() for cell in row.cells]
                for row in Table(element, document).rows
            ]
            rows = _trim_trailing_empty(rows)
            if rows:
                parts.append(_rows_to_text(rows))

    return '\n\n'.join(parts)


def _extract_xlsx(data: bytes) -> str:
    _require_magic(data, _ZIP_MAGIC, 'Excel (.xlsx)')
    _guard_zip_bomb(data)

    import openpyxl

    # read_only streams the sheet instead of building the whole object graph;
    # data_only yields each formula's cached result rather than "=SUM(A1:A9)".
    workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        sections: List[str] = []
        for sheet in workbook.worksheets:
            rows = _trim_trailing_empty(
                [
                    [_cell_to_str(value) for value in row]
                    for row in sheet.iter_rows(values_only=True)
                ]
            )
            if rows:
                sections.append(f'### Sheet: {sheet.title}\n{_rows_to_text(rows)}')
        return '\n\n'.join(sections)
    finally:
        workbook.close()


def _extract_xls(data: bytes) -> str:
    _require_magic(data, _OLE2_MAGIC, 'Excel (.xls)')

    import xlrd

    try:
        workbook = xlrd.open_workbook(file_contents=data)
    except Exception as exc:
        raise DocumentExtractionError(f'Could not read the .xls file: {exc}') from exc

    sections: List[str] = []
    for sheet in workbook.sheets():
        rows = _trim_trailing_empty(
            [
                [_cell_to_str(value) for value in sheet.row_values(index)]
                for index in range(sheet.nrows)
            ]
        )
        if rows:
            sections.append(f'### Sheet: {sheet.name}\n{_rows_to_text(rows)}')
    return '\n\n'.join(sections)


def _extract_doc(data: bytes) -> str:
    """Extract text from a legacy binary .doc via antiword.

    The only format here that needs an external program. antiword is small and
    packaged in Debian, but it is unmaintained C parsing untrusted input, so it
    is reached only after the OLE2 magic check and a size check, and it runs
    with no shell and a hard timeout.
    """
    _require_magic(data, _OLE2_MAGIC, 'Word (.doc)')

    with tempfile.NamedTemporaryFile(suffix='.doc', delete=False) as handle:
        os.chmod(handle.name, 0o600)
        handle.write(data)
        handle.flush()
        path = handle.name

    try:
        # `-m UTF-8.txt` selects antiword's UTF-8 output mapping; without it the
        # output follows the container locale and mangles non-ASCII text.
        result = subprocess.run(
            ['antiword', '-m', 'UTF-8.txt', path],
            capture_output=True,
            timeout=ANTIWORD_TIMEOUT_SECONDS,
            check=False,
            shell=False,
        )
    except FileNotFoundError as exc:
        logger.error('antiword is not installed; cannot extract .doc files')
        raise DocumentExtractionError(
            'Legacy .doc extraction is unavailable on this server. '
            'Convert the file to .docx and upload it again.'
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise DocumentExtractionError(
            f'Timed out reading the .doc file after '
            f'{ANTIWORD_TIMEOUT_SECONDS} seconds.'
        ) from exc
    finally:
        try:
            os.unlink(path)
        except OSError:
            logger.warning(f'Could not remove temporary file {path}')

    if result.returncode != 0:
        # stderr can name the temp path; log it, but keep it out of the response.
        logger.error(
            f'antiword exited {result.returncode}: '
            f'{result.stderr.decode("utf-8", errors="replace").strip()}'
        )
        raise DocumentExtractionError(
            'Could not read the .doc file. It may be corrupt, password '
            'protected, or saved in a format antiword does not support.'
        )

    return _decode_text(result.stdout)


_EXTRACTORS: Dict[str, Callable[[bytes], str]] = {
    TEXT_MIME_TYPE: _extract_plain_text,
    CSV_MIME_TYPE: _extract_csv,
    DOC_MIME_TYPE: _extract_doc,
    DOCX_MIME_TYPE: _extract_docx,
    XLS_MIME_TYPE: _extract_xls,
    XLSX_MIME_TYPE: _extract_xlsx,
}


def _resolve_extractor(data: bytes, mime_type: str) -> Callable[[bytes], str]:
    """Pick the handler, correcting the one mime type that is routinely wrong.

    Windows reports ``.csv`` as ``application/vnd.ms-excel``, so that mime type
    alone cannot distinguish a real legacy spreadsheet from a comma-separated
    text file. A genuine .xls is an OLE2 compound file; anything else under that
    mime type is treated as CSV.
    """
    if mime_type == XLS_MIME_TYPE and not data.startswith(_OLE2_MAGIC):
        return _extract_csv
    return _EXTRACTORS[mime_type]


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return (
        f'{text[:max_chars]}\n\n'
        f'[Truncated: showing the first {max_chars} of {len(text)} '
        f'extracted characters.]'
    )


def extract_document_text(
    data: bytes,
    mime_type: str,
    file_name: Optional[str] = None,
    *,
    max_chars: Optional[int] = None,
) -> str:
    """Convert a document to a text block ready to send to a model.

    Args:
        data: The raw document bytes.
        mime_type: A mime type from ``EXTRACTABLE_DOCUMENT_MIME_TYPES``.
        file_name: Original name of the upload, if known. Included in the output
            because agents are routinely asked to report it, and unlike the
            media blocks in flo_ai there is no separate field carrying it.
        max_chars: Override the extracted-character budget.

    Returns:
        The extracted text, prefixed with a line naming the source file and
        suffixed with a truncation marker if the budget was exceeded. Empty
        documents return a line saying so rather than an empty string, so the
        model can tell an empty file from a failed upload.

    Raises:
        DocumentExtractionError: The file could not be read.
    """
    if mime_type not in _EXTRACTORS:
        raise DocumentExtractionError(f'Cannot extract text from `{mime_type}`.')

    if len(data) > MAX_DOCUMENT_BYTES:
        raise DocumentExtractionError(
            f'File is {len(data)} bytes, over the {MAX_DOCUMENT_BYTES} byte '
            f'limit for text extraction.'
        )

    extractor = _resolve_extractor(data, mime_type)
    try:
        text = extractor(data)
    except DocumentExtractionError:
        raise
    except Exception as exc:
        logger.error(f'Text extraction failed for mime_type={mime_type}: {exc}')
        raise DocumentExtractionError(
            f'Could not extract text from the file: {exc}'
        ) from exc

    budget = MAX_EXTRACTED_CHARS if max_chars is None else max_chars
    text = _truncate(text.strip(), budget)

    label = f'"{file_name}"' if file_name else f'an uploaded {mime_type} file'
    if not text:
        return f'Contents of {label}: the file contains no extractable text.'
    return f'Contents of {label} (text extracted from the uploaded file):\n\n{text}'
