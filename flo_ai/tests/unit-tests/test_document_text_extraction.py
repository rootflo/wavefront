"""Tests for Office/CSV text extraction.

Fixtures for the OOXML formats are generated in-process by the same libraries
that read them, so there are no binary blobs to maintain. The two legacy binary
formats have no pure-Python writer, so those tests exercise the guards around
the readers rather than a real round trip.
"""

import io
import re
import zipfile
from unittest.mock import patch

import pytest
from flo_ai.utils.document_text_extraction import (
    CSV_MIME_TYPE,
    DOC_MIME_TYPE,
    DOCX_MIME_TYPE,
    TEXT_MIME_TYPE,
    XLS_MIME_TYPE,
    XLSX_MIME_TYPE,
    EXTRACTABLE_DOCUMENT_MIME_TYPES,
    DocumentExtractionError,
    _collect_rows,
    extract_document_text,
)

OLE2_HEADER = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'


def build_docx(paragraphs=('Hello world',), table=None) -> bytes:
    from docx import Document

    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    if table:
        added = document.add_table(rows=len(table), cols=len(table[0]))
        for row_index, row in enumerate(table):
            for col_index, value in enumerate(row):
                added.cell(row_index, col_index).text = value

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def build_xlsx(sheets) -> bytes:
    import openpyxl

    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for title, rows in sheets.items():
        sheet = workbook.create_sheet(title=title)
        for row in rows:
            sheet.append(row)

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def with_declared_dimension(data: bytes, ref: str) -> bytes:
    """Rewrite the first sheet's declared used range, as a careless writer would."""
    source = zipfile.ZipFile(io.BytesIO(data))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename == 'xl/worksheets/sheet1.xml':
                content = re.sub(
                    rb'<dimension ref="[^"]*"',
                    f'<dimension ref="{ref}"'.encode(),
                    content,
                )
            target.writestr(info, content)
    return buffer.getvalue()


class TestPlainFormats:
    def test_csv_round_trip(self):
        result = extract_document_text(
            b'region,revenue\nEast,1200\n', CSV_MIME_TYPE, 'q3.csv'
        )

        assert 'region,revenue' in result
        assert 'East,1200' in result
        assert 'Contents of "q3.csv"' in result

    def test_plain_text_round_trip(self):
        """text/plain was rejected outright before this feature."""
        result = extract_document_text(b'just some notes', TEXT_MIME_TYPE, 'notes.txt')

        assert 'just some notes' in result

    def test_utf8_bom_is_stripped(self):
        """Excel writes a BOM on CSV export; it must not reach the model."""
        result = extract_document_text(
            'name,city\nJosé,Köln\n'.encode('utf-8-sig'),
            CSV_MIME_TYPE,
            'people.csv',
        )

        assert '﻿' not in result
        assert 'José' in result
        assert 'Köln' in result

    def test_cp1252_fallback_does_not_raise(self):
        result = extract_document_text(b'caf\xe9,1', CSV_MIME_TYPE, 'legacy.csv')

        assert 'caf' in result

    def test_empty_file_is_reported_not_silently_blank(self):
        result = extract_document_text(b'', TEXT_MIME_TYPE, 'empty.txt')

        assert 'no extractable text' in result


class TestDocx:
    def test_paragraphs_are_extracted(self):
        data = build_docx(paragraphs=('First para', 'Second para'))

        result = extract_document_text(data, DOCX_MIME_TYPE, 'report.docx')

        assert 'First para' in result
        assert 'Second para' in result

    def test_table_content_is_extracted(self):
        """The reason for python-docx over docx2txt, which drops tables."""
        data = build_docx(
            paragraphs=('Summary follows',),
            table=[['Region', 'Revenue'], ['East', '1200']],
        )

        result = extract_document_text(data, DOCX_MIME_TYPE, 'report.docx')

        assert 'Summary follows' in result
        assert 'Region,Revenue' in result
        assert 'East,1200' in result

    def test_non_zip_content_is_rejected(self):
        with pytest.raises(DocumentExtractionError) as exc_info:
            extract_document_text(b'not a zip at all', DOCX_MIME_TYPE, 'fake.docx')

        assert 'does not look like' in str(exc_info.value)


class TestXlsx:
    def test_sheets_are_labelled_and_extracted(self):
        data = build_xlsx(
            {
                'Summary': [['Region', 'Revenue'], ['East', 1200]],
                'Detail': [['SKU'], ['A-1']],
            }
        )

        result = extract_document_text(data, XLSX_MIME_TYPE, 'budget.xlsx')

        assert '### Sheet: Summary' in result
        assert '### Sheet: Detail' in result
        assert 'Region,Revenue' in result
        assert 'A-1' in result

    def test_integers_do_not_become_floats(self):
        """openpyxl returns every number as a float; 1200.0 would be noise."""
        data = build_xlsx({'S': [['count'], [1200]]})

        result = extract_document_text(data, XLSX_MIME_TYPE, 'n.xlsx')

        assert '1200' in result
        assert '1200.0' not in result

    def test_non_zip_content_is_rejected(self):
        with pytest.raises(DocumentExtractionError):
            extract_document_text(b'plain text', XLSX_MIME_TYPE, 'fake.xlsx')

    def test_zip_bomb_is_rejected(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            # Compresses to a few kB, so the ratio check trips well before the
            # absolute uncompressed cap.
            archive.writestr('xl/worksheets/sheet1.xml', b'\0' * (8 * 1024 * 1024))

        with pytest.raises(DocumentExtractionError) as exc_info:
            extract_document_text(buffer.getvalue(), XLSX_MIME_TYPE, 'bomb.xlsx')

        assert 'compression ratio' in str(exc_info.value)


class TestWindowsCsvAmbiguity:
    def test_csv_declared_as_vnd_ms_excel_is_read_as_csv(self):
        """Windows reports .csv as application/vnd.ms-excel.

        Dispatching on the declared mime alone would hand this to the .xls
        reader and fail every CSV upload from a Windows browser.
        """
        result = extract_document_text(
            b'region,revenue\nEast,1200\n', XLS_MIME_TYPE, 'q3.csv'
        )

        assert 'East,1200' in result

    def test_real_xls_still_routes_to_the_xls_reader(self):
        """An OLE2 header under the same mime must not be treated as text."""
        with pytest.raises(DocumentExtractionError):
            extract_document_text(
                OLE2_HEADER + b'truncated garbage', XLS_MIME_TYPE, 'book.xls'
            )


_DOC_ENABLED = DOC_MIME_TYPE in EXTRACTABLE_DOCUMENT_MIME_TYPES


@pytest.mark.skipif(
    _DOC_ENABLED, reason='.doc is enabled; these pin the deferred contract only'
)
class TestDocDeferred:
    """Legacy .doc is not implemented yet; pin the contract until it is.

    Skips itself once DOC_MIME_TYPE joins EXTRACTABLE_DOCUMENT_MIME_TYPES, so
    enabling .doc does not also mean hunting down these tests. Add real .doc
    round-trip tests alongside the reader.
    """

    def test_doc_is_not_advertised_as_extractable(self):
        """Callers gate on this set, so .doc must be rejected up front."""
        assert DOC_MIME_TYPE not in EXTRACTABLE_DOCUMENT_MIME_TYPES

    def test_doc_extraction_raises_an_actionable_error(self):
        with pytest.raises(DocumentExtractionError) as exc_info:
            extract_document_text(OLE2_HEADER + b'body', DOC_MIME_TYPE, 'old.doc')

        assert '.docx' in str(exc_info.value)


class TestBudgets:
    def test_long_text_is_truncated_with_a_visible_marker(self):
        result = extract_document_text(
            b'x' * 5000, TEXT_MIME_TYPE, 'big.txt', max_chars=100
        )

        # The marker quotes no total: spreadsheet extraction stops once the
        # budget is met, so a total here would be what was read, not what the
        # file holds.
        assert '[Truncated at 100 characters' in result

    def test_text_within_budget_is_not_marked(self):
        result = extract_document_text(
            b'short', TEXT_MIME_TYPE, 'ok.txt', max_chars=100
        )

        assert 'Truncated' not in result

    def test_oversized_upload_is_rejected(self):
        with patch('flo_ai.utils.document_text_extraction.MAX_DOCUMENT_BYTES', 10):
            with pytest.raises(DocumentExtractionError) as exc_info:
                extract_document_text(b'x' * 100, TEXT_MIME_TYPE, 'big.txt')

        assert 'byte limit' in str(exc_info.value)


class TestDispatch:
    def test_unsupported_mime_is_rejected(self):
        with pytest.raises(DocumentExtractionError):
            extract_document_text(b'data', 'application/pdf', 'doc.pdf')

    def test_file_name_is_carried_into_the_text(self):
        """TextMessageContent has no file_name field, so it rides in the body."""
        result = extract_document_text(b'body', TEXT_MIME_TYPE, 'quarterly.txt')

        assert 'quarterly.txt' in result

    def test_missing_file_name_still_produces_a_header(self):
        result = extract_document_text(b'body', TEXT_MIME_TYPE, None)

        assert 'Contents of' in result


class TestUtf16AndNullBytes:
    """UTF-16 is what PowerShell Export-Csv and Excel's Unicode Text produce.

    cp1252 maps almost every byte, so it "succeeds" on UTF-16 and yields the
    text interleaved with NULs. U+0000 is rejected by the provider APIs and by
    Postgres, and the extracted text reaches both -- it is sent to the model
    and stored in the execution trace.
    """

    @pytest.mark.parametrize('encoding', ['utf-16', 'utf-16-le', 'utf-16-be'])
    def test_utf16_csv_decodes_without_null_bytes(self, encoding):
        data = 'region,revenue\nEast,1200\n'.encode(encoding)

        result = extract_document_text(data, CSV_MIME_TYPE, 'ps-export.csv')

        assert '\x00' not in result
        assert 'region,revenue' in result
        assert 'East,1200' in result

    def test_raw_null_bytes_in_a_text_file_are_scrubbed(self):
        """A .txt holding raw NULs must not carry them through.

        cp1252 maps 0x00 straight to U+0000, so without the scrub this reaches
        the provider and the stored trace verbatim.
        """
        result = extract_document_text(
            b'before\x00\x00after', TEXT_MIME_TYPE, 'binary-ish.txt'
        )

        assert '\x00' not in result
        assert 'beforeafter' in result

    def test_utf16_text_file_decodes_cleanly(self):
        data = 'quarterly notes\n'.encode('utf-16')

        result = extract_document_text(data, TEXT_MIME_TYPE, 'notes.txt')

        assert '\x00' not in result
        assert 'quarterly notes' in result


class TestContentControls:
    """Word content controls (<w:sdt>) wrap content in templates and forms."""

    @staticmethod
    def _docx_with_sdt(inner_xml: str) -> bytes:
        from docx import Document
        from docx.oxml import parse_xml

        namespace = (
            'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
        )
        document = Document()
        document.add_paragraph('Outside the control')
        document.element.body.append(
            parse_xml(
                f'<w:sdt {namespace}><w:sdtPr/>'
                f'<w:sdtContent>{inner_xml}</w:sdtContent></w:sdt>'
            )
        )
        buffer = io.BytesIO()
        document.save(buffer)
        return buffer.getvalue()

    def test_paragraph_inside_content_control_is_extracted(self):
        data = self._docx_with_sdt(
            '<w:p><w:r><w:t>Clause 7: termination</w:t></w:r></w:p>'
        )

        result = extract_document_text(data, DOCX_MIME_TYPE, 'contract.docx')

        assert 'Outside the control' in result
        assert 'Clause 7: termination' in result

    def test_table_inside_content_control_is_extracted(self):
        row = (
            '<w:tr>'
            '<w:tc><w:p><w:r><w:t>Region</w:t></w:r></w:p></w:tc>'
            '<w:tc><w:p><w:r><w:t>East</w:t></w:r></w:p></w:tc>'
            '</w:tr>'
        )

        data = self._docx_with_sdt(f'<w:tbl>{row}</w:tbl>')

        result = extract_document_text(data, DOCX_MIME_TYPE, 'form.docx')

        assert 'Region,East' in result


class TestSpreadsheetEarlyTermination:
    def test_collect_rows_stops_at_the_budget(self):
        """Deterministic check that the reader stops pulling rows.

        Timing would be flaky, so count what the iterator actually yields: a
        spreadsheet's used range can run to hundreds of thousands of rows and
        reading all of them blocks the request for the >99% that is discarded.
        """
        pulled = 0

        def endless():
            nonlocal pulled
            while True:
                pulled += 1
                yield ('some filler text value', 'another column')

        rows, used = _collect_rows(endless(), 1000)

        assert used >= 1000
        assert pulled < 100, f'read {pulled} rows for a 1000 char budget'
        assert len(rows) == pulled

    def test_budget_spans_the_workbook_not_each_sheet(self):
        data = build_xlsx(
            {
                'One': [[f'row {i} of sheet one'] for i in range(200)],
                'Two': [[f'row {i} of sheet two'] for i in range(200)],
            }
        )

        result = extract_document_text(data, XLSX_MIME_TYPE, 'two.xlsx', max_chars=200)

        assert 'Truncated at 200 characters' in result
        # The budget was spent on the first sheet, so the second never starts.
        assert '### Sheet: Two' not in result

    def test_padding_cells_do_not_spend_the_budget(self):
        """A used range stretched to column XFD pads each row to 16k cells.

        Counted before trimming, the first row alone would exhaust this budget.
        """
        padded_row = ('East', '1200', 'Q1') + (None,) * 16381

        rows, used = _collect_rows(iter([padded_row] * 50), 1000)

        assert len(rows) == 50
        assert rows[0] == ['East', '1200', 'Q1']
        assert used < 1000

    def test_blank_rows_still_spend_the_budget(self):
        """Trimmed to nothing, a blank row must still cost something, or a
        sheet padded with empty rows is read to the very end."""
        pulled = 0

        def blank_rows():
            nonlocal pulled
            for _ in range(10_000):
                pulled += 1
                yield (None, None, None)

        rows, used = _collect_rows(blank_rows(), 100)

        assert pulled <= 100, f'read {pulled} blank rows for a 100 char budget'
        assert rows == []

    def test_early_stop_is_marked_even_when_the_text_lands_under_the_cap(self):
        """Blank rows spend budget but are trimmed from the output, so text
        read up to the budget can end up shorter than it. The marker must not
        depend on the length alone."""
        data = build_xlsx(
            {
                'S': [['x' * 50]] + [[]] * 49 + [['tail']],
                'Later': [['never read']],
            }
        )

        result = extract_document_text(
            data, XLSX_MIME_TYPE, 'gappy.xlsx', max_chars=100
        )

        assert 'Truncated at 100 characters' in result
        assert 'tail' not in result
        assert 'never read' not in result

    @pytest.mark.parametrize(
        'declared',
        [
            # Stray formatting: every row padded out to the last column.
            'A1:XFD30',
            # A writer declaring one cell over a full sheet.
            'A1:A1',
        ],
    )
    def test_declared_used_range_does_not_limit_what_is_read(self, declared):
        data = with_declared_dimension(
            build_xlsx({'S': [[f'row {i}'] for i in range(30)]}), declared
        )

        result = extract_document_text(data, XLSX_MIME_TYPE, 'odd.xlsx', max_chars=2000)

        assert 'row 0' in result
        assert 'row 29' in result
        assert 'Truncated' not in result

    def test_small_sheet_is_unaffected(self):
        data = build_xlsx({'S': [['Region', 'Revenue'], ['East', 1200]]})

        result = extract_document_text(data, XLSX_MIME_TYPE, 'small.xlsx')

        assert 'Truncated' not in result
        assert 'East,1200' in result
