"""Text extraction for Office and plain-text documents.

No provider flo_ai supports reads Word or Excel through the API shape flo_ai
uses: OpenAI's Chat Completions takes PDF only, Anthropic's document block takes
PDF and plain text, and Gemini reads PDF meaningfully and little else. So
``BaseLLM.format_document_in_message`` converts these formats to text here and
hands the model an ordinary text block. That works identically on every
provider, including ones with no document support at all.

PDF is deliberately not handled here. It keeps its native path -- a document
block where the provider accepts one, rasterized pages where it does not --
because a vision model reading the page beats extracted text for PDFs.

A note on trust: the mime type reaching this module usually comes from an
end user, and here it selects which parser runs. So every handler that needs a
specific container verifies its magic bytes first rather than trusting the
declared type.
"""

import csv
import io
import os
import zipfile
from typing import Callable, Dict, List, Optional, Tuple

from flo_ai.utils.logger import logger

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
        # DOC_MIME_TYPE is omitted until _extract_doc is implemented.
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


class DocumentExtractionError(Exception):
    """Raised when a document cannot be converted to text.

    Callers at the API boundary turn this into a 400. The message is safe to
    return to the caller: it never contains document content.
    """


_UTF16_BOMS = (b'\xff\xfe', b'\xfe\xff')


def _decode_text(data: bytes) -> str:
    """Decode bytes that are meant to be text, tolerating common encodings.

    ``utf-8-sig`` first because spreadsheets exported from Excel carry a BOM.

    UTF-16 is tried next, and only when the data actually opens with a UTF-16
    BOM. Order matters: cp1252 maps almost every byte value, so it "succeeds"
    on UTF-16 input and yields the text interleaved with NULs
    (``'r\\x00e\\x00g\\x00i\\x00o\\x00n'``). PowerShell ``Export-Csv`` and
    Excel's "Save As Unicode Text" both default to UTF-16 LE, so this is an
    ordinary file, not an edge case.

    cp1252 then covers stray bytes in Windows-authored CSVs, and latin-1 last
    because it cannot fail -- there is always a result rather than a 400 on a
    single bad byte.
    """
    encodings = ('utf-8-sig', 'utf-16', 'cp1252')
    for encoding in encodings:
        if encoding == 'utf-16' and not data.startswith(_UTF16_BOMS):
            continue
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


def _trim_row(row: List[str]) -> List[str]:
    """Drop a row's trailing empty cells, in place."""
    while row and not row[-1].strip():
        row.pop()
    return row


def _trim_trailing_empty(rows: List[List[str]]) -> List[List[str]]:
    """Drop trailing empty cells per row, and trailing empty rows.

    Spreadsheet readers report the full used range, which is routinely padded
    with hundreds of empty cells from stray formatting.
    """
    trimmed = [_trim_row(row) for row in rows]
    while trimmed and not any(cell.strip() for cell in trimmed[-1]):
        trimmed.pop()
    return trimmed


# Every extractor takes (data, budget) and returns (text, stopped_early) so the
# dispatch table stays uniform. Only the spreadsheet readers act on the budget:
# the rest produce their text in a single decode or parse, where stopping early
# would save nothing, so they always report False and leave the final cap to
# `_truncate`.


def _extract_plain_text(data: bytes, budget: int) -> Tuple[str, bool]:
    return _decode_text(data), False


def _extract_csv(data: bytes, budget: int) -> Tuple[str, bool]:
    # Already delimited text. Decode and pass through rather than re-serializing:
    # round-tripping through the csv module would normalize the author's
    # delimiter and quoting for no benefit.
    return _decode_text(data), False


def _collect_docx_element(element, document, parts: List[str]) -> None:
    """Append the text of one body element, descending into content controls.

    Handles the three body children that carry text. ``w:sdt`` is a structured
    document tag -- Word's content control -- and wraps its real content in a
    ``w:sdtContent`` child. Documents built from templates, forms and contracts
    put whole sections inside them, and matching only ``w:p``/``w:tbl`` at the
    top level drops that text with no error.
    """
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    tag = element.tag
    if tag.endswith('}p'):
        text = Paragraph(element, document).text.strip()
        if text:
            parts.append(text)
    elif tag.endswith('}tbl'):
        rows = _trim_trailing_empty(
            [
                [cell.text.strip() for cell in row.cells]
                for row in Table(element, document).rows
            ]
        )
        if rows:
            parts.append(_rows_to_text(rows))
    elif tag.endswith('}sdt'):
        for child in element.iterchildren():
            if child.tag.endswith('}sdtContent'):
                for nested in child.iterchildren():
                    _collect_docx_element(nested, document, parts)


def _extract_docx(data: bytes, budget: int) -> Tuple[str, bool]:
    _require_magic(data, _ZIP_MAGIC, 'Word (.docx)')
    _guard_zip_bomb(data)

    from docx import Document

    document = Document(io.BytesIO(data))

    # Walk the body in document order rather than `document.paragraphs` then
    # `document.tables`: in a typical report the tables carry most of the
    # content, and reading them all after the prose loses which section each
    # belonged to.
    parts: List[str] = []
    for element in document.element.body.iterchildren():
        _collect_docx_element(element, document, parts)

    return '\n\n'.join(parts), False


def _collect_rows(row_values, budget: int) -> tuple[List[List[str]], int]:
    """Format rows from an iterable, stopping once `budget` chars are collected.

    Spreadsheets report their whole used range, which stray formatting can
    stretch to hundreds of thousands of rows. Reading all of it and then
    truncating meant a 1.6 MB / 100k-row file took ~19 seconds and threw away
    over 99% of the result -- on the sync endpoints, that is the request
    blocking. Stopping at the budget makes the cost proportional to what the
    model will actually see.

    Each row is trimmed before it is counted. The same stray formatting can
    stretch the range out to column XFD, and counting that padding charged
    ~16k characters per row -- the budget ran out after about a dozen rows of
    three real cells each.

    Returns the rows and the character count, which the caller carries across
    sheets so the budget spans the workbook rather than resetting per sheet.
    """
    rows: List[List[str]] = []
    used = 0
    for raw_row in row_values:
        row = _trim_row([_cell_to_str(value) for value in raw_row])
        rows.append(row)
        # One separator per cell: the commas plus the newline _rows_to_text
        # will add. A blank row still costs its newline; at zero, a sheet
        # padded with a million empty rows would be read to the end.
        used += sum(len(cell) for cell in row) + max(len(row), 1)
        if used >= budget:
            break
    return _trim_trailing_empty(rows), used


def _extract_xlsx(data: bytes, budget: int) -> Tuple[str, bool]:
    _require_magic(data, _ZIP_MAGIC, 'Excel (.xlsx)')
    _guard_zip_bomb(data)

    import openpyxl

    # read_only streams the sheet instead of building the whole object graph;
    # data_only yields each formula's cached result rather than "=SUM(A1:A9)".
    workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        sections: List[str] = []
        remaining = budget
        for sheet in workbook.worksheets:
            if remaining <= 0:
                break
            # read_only pads every row out to the sheet's declared used range,
            # which is wrong in both directions often enough to matter: stray
            # formatting stretches it to column XFD, so each row arrives as
            # 16k cells to convert and trim, and some writers declare A1:A1
            # over a full sheet, which hides everything past the first cell.
            # Without it, each row ends at its last stored cell.
            sheet.reset_dimensions()
            rows, used = _collect_rows(sheet.iter_rows(values_only=True), remaining)
            remaining -= used
            if rows:
                sections.append(f'### Sheet: {sheet.title}\n{_rows_to_text(rows)}')
        # A spent budget means reading stopped there, mid-sheet or before a
        # later sheet started.
        return '\n\n'.join(sections), remaining <= 0
    finally:
        workbook.close()


def _extract_xls(data: bytes, budget: int) -> Tuple[str, bool]:
    _require_magic(data, _OLE2_MAGIC, 'Excel (.xls)')

    import xlrd

    try:
        workbook = xlrd.open_workbook(file_contents=data)
    except Exception as exc:
        raise DocumentExtractionError(f'Could not read the .xls file: {exc}') from exc

    sections: List[str] = []
    remaining = budget
    for sheet in workbook.sheets():
        if remaining <= 0:
            break
        rows, used = _collect_rows(
            (sheet.row_values(index) for index in range(sheet.nrows)), remaining
        )
        remaining -= used
        if rows:
            sections.append(f'### Sheet: {sheet.name}\n{_rows_to_text(rows)}')
    return '\n\n'.join(sections), remaining <= 0


def _extract_doc(data: bytes, budget: int) -> Tuple[str, bool]:
    """Legacy binary .doc (Word 97-2003). Not implemented yet.

    Deferred pending a choice of reader. The obvious one, antiword, is a system
    binary that an SDK cannot install; the candidate pure-Python readers are
    still being evaluated. DOC_MIME_TYPE is kept out of
    EXTRACTABLE_DOCUMENT_MIME_TYPES until this lands, so callers gating on that
    set reject .doc up front instead of reaching this.
    """
    raise DocumentExtractionError(
        'Legacy .doc files are not supported yet. '
        'Save the file as .docx and upload it again.'
    )


_Extractor = Callable[[bytes, int], Tuple[str, bool]]

_EXTRACTORS: Dict[str, _Extractor] = {
    TEXT_MIME_TYPE: _extract_plain_text,
    CSV_MIME_TYPE: _extract_csv,
    DOC_MIME_TYPE: _extract_doc,
    DOCX_MIME_TYPE: _extract_docx,
    XLS_MIME_TYPE: _extract_xls,
    XLSX_MIME_TYPE: _extract_xlsx,
}


def _resolve_extractor(data: bytes, mime_type: str) -> _Extractor:
    """Pick the handler, correcting the one mime type that is routinely wrong.

    Windows reports ``.csv`` as ``application/vnd.ms-excel``, so that mime type
    alone cannot distinguish a real legacy spreadsheet from a comma-separated
    text file. A genuine .xls is an OLE2 compound file; anything else under that
    mime type is treated as CSV.
    """
    if mime_type == XLS_MIME_TYPE and not data.startswith(_OLE2_MAGIC):
        return _extract_csv
    return _EXTRACTORS[mime_type]


def _truncate(text: str, max_chars: int, stopped_early: bool = False) -> str:
    """Cap the text, marking the cut so the model knows content is missing.

    The marker deliberately does not quote a total. Spreadsheet extraction now
    stops reading once it has enough, so the length here is what was collected,
    not what the file holds -- reporting it as a total would understate the
    document.

    `stopped_early` forces the marker. The spreadsheet budget is an estimate
    taken before trailing blank rows and whitespace are stripped, so text read
    up to the budget can still land under `max_chars`, and the length test
    alone would then drop the marker.
    """
    if len(text) <= max_chars and not stopped_early:
        return text
    return (
        f'{text[:max_chars]}\n\n'
        f'[Truncated at {max_chars} characters; the rest of this file was '
        f'not included.]'
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
        suffixed with a truncation marker if the budget was reached. Empty
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

    budget = MAX_EXTRACTED_CHARS if max_chars is None else max_chars

    extractor = _resolve_extractor(data, mime_type)
    try:
        text, stopped_early = extractor(data, budget)
    except DocumentExtractionError:
        raise
    except Exception as exc:
        logger.error(f'Text extraction failed for mime_type={mime_type}: {exc}')
        raise DocumentExtractionError(
            f'Could not extract text from the file: {exc}'
        ) from exc

    # U+0000 is rejected by the provider APIs, and by Postgres wherever a
    # caller persists the conversation.
    #
    # Reachable on the decoded-text paths: cp1252 maps 0x00 to U+0000, so a
    # UTF-16 file read as cp1252 or a .txt holding raw NULs produces them. OOXML forbids NUL outright, so for docx/xlsx this is
    # belt-and-braces -- done here rather than in `_decode_text` so no future
    # extractor has to remember it.
    text = text.replace('\x00', '')
    text = _truncate(text.strip(), budget, stopped_early)

    label = f'"{file_name}"' if file_name else f'an uploaded {mime_type} file'
    if not text:
        return f'Contents of {label}: the file contains no extractable text.'
    return f'Contents of {label} (text extracted from the uploaded file):\n\n{text}'
