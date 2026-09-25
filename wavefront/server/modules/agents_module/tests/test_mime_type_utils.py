import base64
from io import BytesIO

import pytest
from fastapi import HTTPException
from PIL import Image

from agents_module.utils.input_processing_utils import (
    process_inference_inputs,
    validate_inference_inputs_media,
)
from agents_module.utils.mime_type_utils import (
    MAX_FILE_NAME_LENGTH,
    SUPPORTED_DOCUMENT_MIME_TYPES,
    SUPPORTED_IMAGE_MIME_TYPES,
    ensure_safe_file_name,
    ensure_supported_document_mime_type,
    ensure_supported_image_mime_type,
    normalize_mime_type,
    resolve_mime_type,
    split_data_url,
)

PNG_B64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
# A structurally valid one-page PDF: the gate parses documents now, so a
# `%PDF-` prefix alone is no longer accepted as one.
PDF_B64 = 'JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjguMgoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjguMik+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0NvdW50IDEvS2lkc1s0IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDw+PgplbmRvYmoKCjQgMCBvYmoKPDwvVHlwZS9QYWdlL01lZGlhQm94WzAgMCA3MiA3Ml0vUm90YXRlIDAvUmVzb3VyY2VzIDMgMCBSL1BhcmVudCAyIDAgUj4+CmVuZG9iagoKeHJlZgowIDUKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDQyIDAwMDAwIG4gCjAwMDAwMDAxMjAgMDAwMDAgbiAKMDAwMDAwMDE3MiAwMDAwMCBuIAowMDAwMDAwMTkzIDAwMDAwIG4gCgp0cmFpbGVyCjw8L1NpemUgNS9Sb290IDEgMCBSL0lEWzxDM0ExQzJCNzM1QzNBMDczNTk0NEMzQURDMjhEQzI4Qj48QjYzOEIzMjRCNUUwQzQ3Q0NEMTRBNUMzMjYzMDg2RkQ+XT4+CnN0YXJ0eHJlZgoyODIKJSVFT0YK'


class TestNormalizeMimeType:
    """Test cases for normalize_mime_type"""

    def test_lowercases_and_strips(self):
        assert normalize_mime_type('  IMAGE/PNG  ') == 'image/png'

    def test_drops_parameters(self):
        assert normalize_mime_type('application/pdf; charset=binary') == (
            'application/pdf'
        )

    def test_resolves_jpg_alias(self):
        assert normalize_mime_type('image/jpg') == 'image/jpeg'

    def test_non_string_returns_none(self):
        assert normalize_mime_type(None) is None
        assert normalize_mime_type(123) is None

    def test_empty_returns_none(self):
        assert normalize_mime_type('   ') is None


class TestSplitDataUrl:
    """Test cases for split_data_url"""

    def test_splits_base64_data_url(self):
        assert split_data_url(f'data:application/pdf;base64,{PDF_B64}') == (
            'application/pdf',
            PDF_B64,
        )

    def test_splits_with_extra_parameters(self):
        mime, payload = split_data_url(f'data:image/png;charset=utf-8;base64,{PNG_B64}')
        assert mime == 'image/png'
        assert payload == PNG_B64

    def test_normalizes_mime_in_data_url(self):
        mime, _ = split_data_url(f'data:IMAGE/JPG;base64,{PNG_B64}')
        assert mime == 'image/jpeg'

    def test_non_base64_data_url_not_split(self):
        """Percent-encoded payloads are not base64 - decoding them is garbage"""
        assert split_data_url('data:text/plain;charset=utf-8,hello%20world') == (
            None,
            None,
        )

    def test_plain_base64_not_split(self):
        assert split_data_url(PDF_B64) == (None, None)

    def test_non_string_not_split(self):
        assert split_data_url(None) == (None, None)

    def test_malformed_data_url_not_split(self):
        assert split_data_url('data:invalid_format') == (None, None)


class TestResolveMimeType:
    """Test cases for the resolution order of resolve_mime_type"""

    def test_explicit_mime_type_wins(self):
        resolved = resolve_mime_type(
            mime_type='image/png',
            base64_value='data:image/gif;base64,abc',
            file_name='x.webp',
        )
        assert resolved == 'image/png'

    def test_falls_back_to_data_url(self):
        assert resolve_mime_type(base64_value='data:image/gif;base64,abc') == (
            'image/gif'
        )

    def test_falls_back_to_file_name(self):
        assert resolve_mime_type(file_name='invoice.PDF') == 'application/pdf'

    def test_falls_back_to_url(self):
        assert resolve_mime_type(url='https://x.test/a/b/report.pdf?sig=1') == (
            'application/pdf'
        )

    def test_unknown_extension_returns_none(self):
        assert resolve_mime_type(file_name='notes.xyz') is None

    def test_nothing_resolvable_returns_none(self):
        assert resolve_mime_type() is None


class TestEnsureSupportedImageMimeType:
    """Test cases for the image gate"""

    @pytest.mark.parametrize('mime_type', sorted(SUPPORTED_IMAGE_MIME_TYPES))
    def test_supported_types_pass(self, mime_type):
        assert ensure_supported_image_mime_type(mime_type=mime_type) == mime_type

    def test_jpg_alias_normalized(self):
        assert ensure_supported_image_mime_type(mime_type='image/jpg') == 'image/jpeg'

    def test_unsupported_type_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            ensure_supported_image_mime_type(mime_type='image/tiff')

        assert exc_info.value.status_code == 400
        assert 'Unsupported image type `image/tiff`' in str(exc_info.value.detail)

    def test_unresolvable_type_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            ensure_supported_image_mime_type(base64_value=PNG_B64)

        assert exc_info.value.status_code == 400
        assert 'Could not determine the mime type' in str(exc_info.value.detail)

    def test_index_included_in_message(self):
        with pytest.raises(HTTPException) as exc_info:
            ensure_supported_image_mime_type(mime_type='image/tiff', index=2)

        assert 'at index 2' in str(exc_info.value.detail)


class TestEnsureSupportedDocumentMimeType:
    """Test cases for the document gate"""

    @pytest.mark.parametrize('mime_type', sorted(SUPPORTED_DOCUMENT_MIME_TYPES))
    def test_supported_types_pass(self, mime_type):
        assert ensure_supported_document_mime_type(mime_type=mime_type) == mime_type

    def test_unsupported_type_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            ensure_supported_document_mime_type(
                mime_type=(
                    'application/vnd.openxmlformats-officedocument'
                    '.wordprocessingml.document'
                )
            )

        assert exc_info.value.status_code == 400
        assert 'Unsupported document type' in str(exc_info.value.detail)

    def test_unsupported_inferred_from_file_name_rejected(self):
        """No mime_type, but the file name gives it away"""
        with pytest.raises(HTTPException) as exc_info:
            ensure_supported_document_mime_type(
                base64_value=PDF_B64, file_name='quarterly.xlsx'
            )

        assert 'spreadsheetml.sheet' in str(exc_info.value.detail)

    def test_unresolvable_type_allowed(self):
        """Missing mime is allowed - the formatter defaults it to PDF"""
        assert ensure_supported_document_mime_type(base64_value=PDF_B64) is None


class TestValidateInferenceInputsMedia:
    """Test cases for the raw-payload walker used by the async endpoints"""

    def test_string_input_passes(self):
        validate_inference_inputs_media('just text')

    def test_text_and_supported_media_pass(self):
        validate_inference_inputs_media(
            [
                {'role': 'user', 'content': 'hello'},
                {'role': 'assistant', 'content': 'hi'},
                {
                    'role': 'user',
                    'content': {'image_base64': f'data:image/png;base64,{PNG_B64}'},
                },
                {
                    'role': 'user',
                    'content': {
                        'document_base64': PDF_B64,
                        'mime_type': 'application/pdf',
                    },
                },
            ]
        )

    def test_unsupported_image_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_inference_inputs_media(
                [
                    {'role': 'user', 'content': 'hello'},
                    {
                        'role': 'user',
                        'content': {
                            'image_base64': PNG_B64,
                            'mime_type': 'image/bmp',
                        },
                    },
                ]
            )

        assert exc_info.value.status_code == 400
        assert 'at index 1' in str(exc_info.value.detail)

    def test_unsupported_document_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_inference_inputs_media(
                [
                    {
                        'role': 'user',
                        'content': {
                            'document_base64': PDF_B64,
                            'mime_type': 'text/plain',
                        },
                    }
                ]
            )

        assert 'Unsupported document type `text/plain`' in str(exc_info.value.detail)

    def test_document_mime_inferred_from_file_name(self):
        """A docx sent with no mime_type is still caught via its file name"""
        with pytest.raises(HTTPException):
            validate_inference_inputs_media(
                [
                    {
                        'role': 'user',
                        'content': {
                            'document_base64': PDF_B64,
                            'file_name': 'contract.docx',
                        },
                    }
                ]
            )

    def test_walker_agrees_with_process_inference_inputs(self):
        """The async gate and the sync gate reject the same payload"""
        payload = [
            {
                'role': 'user',
                'content': {'image_base64': PNG_B64, 'mime_type': 'image/tiff'},
            }
        ]

        with pytest.raises(HTTPException) as walker_exc:
            validate_inference_inputs_media(payload)
        with pytest.raises(HTTPException) as sync_exc:
            process_inference_inputs(payload)

        assert walker_exc.value.status_code == sync_exc.value.status_code
        assert walker_exc.value.detail == sync_exc.value.detail


class TestContentSniffing:
    """The declared type is caller-written; the magic bytes are the file.

    VAPT finding: a PHP script was accepted as an image because every source
    the gate consulted — `mime_type`, the `data:` prefix, `file_name`, `url` —
    is supplied by the same caller sending the bytes.
    """

    PHP = base64.b64encode(b'<?php system($_GET["c"]); ?>').decode('utf-8')
    SVG = base64.b64encode(b'<svg onload=alert(1)></svg>').decode('utf-8')
    HTML = base64.b64encode(b'<html><script>alert(1)</script></html>').decode('utf-8')
    ELF = base64.b64encode(b'\x7fELF\x02\x01\x01' + b'\x00' * 20).decode('utf-8')
    ZIP = base64.b64encode(b'PK\x03\x04' + b'\x00' * 20).decode('utf-8')

    @pytest.mark.parametrize(
        'payload', [PHP, SVG, HTML, ELF, ZIP], ids=['php', 'svg', 'html', 'elf', 'zip']
    )
    @pytest.mark.parametrize('declared', sorted(SUPPORTED_IMAGE_MIME_TYPES))
    def test_non_image_content_rejected_whatever_it_claims(self, payload, declared):
        with pytest.raises(HTTPException) as exc_info:
            ensure_supported_image_mime_type(mime_type=declared, base64_value=payload)

        assert exc_info.value.status_code == 400

    def test_the_reported_payload(self):
        """The exact shape from the report: php bytes, image mime, .php name."""
        with pytest.raises(HTTPException):
            ensure_supported_image_mime_type(
                mime_type='image/png',
                base64_value=self.PHP,
                file_name='shell.php',
            )

    def test_a_benign_extension_does_not_help_either(self):
        """Renaming the payload to .png must not get it through."""
        with pytest.raises(HTTPException):
            ensure_supported_image_mime_type(
                mime_type='image/png',
                base64_value=self.PHP,
                file_name='holiday.png',
            )

    def test_data_url_prefix_does_not_bypass_the_check(self):
        with pytest.raises(HTTPException):
            ensure_supported_image_mime_type(
                base64_value=f'data:image/png;base64,{self.PHP}'
            )

    def test_declared_type_must_match_actual_type(self):
        """A real PNG cannot be passed off as a JPEG."""
        with pytest.raises(HTTPException) as exc_info:
            ensure_supported_image_mime_type(
                mime_type='image/jpeg', base64_value=PNG_B64
            )

        assert 'does not match' in exc_info.value.detail

    def test_genuine_image_still_accepted(self):
        assert (
            ensure_supported_image_mime_type(
                mime_type='image/png', base64_value=PNG_B64
            )
            == 'image/png'
        )

    def test_genuine_pdf_still_accepted(self):
        assert (
            ensure_supported_document_mime_type(
                mime_type='application/pdf', base64_value=PDF_B64
            )
            == 'application/pdf'
        )

    def test_non_pdf_content_rejected_as_document(self):
        with pytest.raises(HTTPException):
            ensure_supported_document_mime_type(
                mime_type='application/pdf', base64_value=self.PHP
            )

    def test_undeclared_document_is_checked_against_pdf(self):
        """A missing mime defaults to PDF downstream, so check it against PDF."""
        with pytest.raises(HTTPException):
            ensure_supported_document_mime_type(base64_value=self.PHP)

    def test_url_inputs_are_not_blocked(self):
        """No base64 to inspect — there is nothing to check here."""
        assert (
            ensure_supported_image_mime_type(url='https://example.com/a.png')
            == 'image/png'
        )

    def test_line_wrapped_base64_is_still_read(self):
        """Wrapped base64 must not slip through by breaking the header slice."""
        wrapped = '\n'.join(self.PHP[i : i + 8] for i in range(0, len(self.PHP), 8))

        with pytest.raises(HTTPException):
            ensure_supported_image_mime_type(
                mime_type='image/png', base64_value=wrapped
            )

    def test_malformed_base64_is_rejected(self):
        """A present-but-undecodable payload fails closed, not silently skipped.

        Returning None for malformed base64 conflated it with an absent
        payload, so the structural parse was skipped and the input accepted.
        """
        with pytest.raises(HTTPException) as exc_info:
            ensure_supported_image_mime_type(
                mime_type='image/png', base64_value='!!!not base64!!!'
            )

        assert exc_info.value.status_code == 400

    def test_malformed_base64_after_valid_header_is_rejected(self):
        """A valid header decodes, but trailing junk must not skip the parse."""
        with pytest.raises(HTTPException):
            ensure_supported_image_mime_type(
                mime_type='image/png',
                base64_value='iVBORw0KGgoAAAANSUhEUgAA' + '@@@not-base64@@@',
            )

    def test_malformed_document_base64_is_rejected(self):
        with pytest.raises(HTTPException):
            ensure_supported_document_mime_type(
                mime_type='application/pdf', base64_value='!!!not base64!!!'
            )

    def test_both_paths_reject_the_payload_identically(self):
        payload = [
            {
                'role': 'user',
                'content': {
                    'image_base64': PHP_AS_IMAGE,
                    'mime_type': 'image/png',
                    'file_name': 'shell.php',
                },
            }
        ]

        with pytest.raises(HTTPException) as walker_exc:
            validate_inference_inputs_media(payload)
        with pytest.raises(HTTPException) as sync_exc:
            process_inference_inputs(payload)

        assert walker_exc.value.detail == sync_exc.value.detail


PHP_AS_IMAGE = TestContentSniffing.PHP


class TestFileNameSafety:
    """The name outlives the bytes: it is stored and returned for display.

    _safe_filename scrubs the storage key, but file_name is persisted verbatim
    and handed back by the execution-read endpoints, so a genuine image called
    `<img src=x onerror=...>.png` passes every content check and still reaches
    a consumer's DOM.
    """

    @pytest.mark.parametrize(
        'name',
        [
            '<img src=x onerror=alert(1)>.png',
            '<script>alert(1)</script>.png',
            'a"onmouseover="alert(1).png',
            "a'onmouseover='alert(1).png",
            'a&lt;b.png',
            'tab\there.png',
            'null\x00byte.png',
            'newline\nhere.png',
        ],
    )
    def test_unsafe_names_rejected(self, name):
        with pytest.raises(HTTPException) as exc_info:
            ensure_safe_file_name(name)

        assert exc_info.value.status_code == 400

    @pytest.mark.parametrize(
        'name',
        [
            'invoice.pdf',
            'holiday photo.png',
            'report-2026_final.pdf',
            'facture-été.pdf',
            'файл.png',
            '文件.pdf',
            'a(1).png',
            'a[1].png',
            'a+b=c.png',
            'a,b;c.png',
            '100%.png',
            'invoices/2026/jan.pdf',
            '../../etc/passwd',
            'a\\b.png',
        ],
    )
    def test_ordinary_names_accepted(self, name):
        """An ASCII allow-list would have rejected half of these."""
        assert ensure_safe_file_name(name) == name

    def test_none_passes_through(self):
        assert ensure_safe_file_name(None) is None

    def test_length_cap(self):
        assert ensure_safe_file_name('a' * MAX_FILE_NAME_LENGTH)

        with pytest.raises(HTTPException) as exc_info:
            ensure_safe_file_name('a' * (MAX_FILE_NAME_LENGTH + 1))

        assert 'too long' in exc_info.value.detail

    def test_non_string_rejected(self):
        with pytest.raises(HTTPException):
            ensure_safe_file_name(123)

    def test_gate_rejects_a_genuine_image_with_an_unsafe_name(self):
        """The bytes are fine; the name is the payload."""
        payload = [
            {
                'role': 'user',
                'content': {
                    'image_base64': PNG_B64,
                    'mime_type': 'image/png',
                    'file_name': '<img src=x onerror=alert(1)>.png',
                },
            }
        ]

        with pytest.raises(HTTPException):
            validate_inference_inputs_media(payload)
        with pytest.raises(HTTPException):
            process_inference_inputs(payload)

    def test_document_names_are_checked_too(self):
        payload = [
            {
                'role': 'user',
                'content': {
                    'document_base64': PDF_B64,
                    'mime_type': 'application/pdf',
                    'file_name': '<script>alert(1)</script>.pdf',
                },
            }
        ]

        with pytest.raises(HTTPException):
            validate_inference_inputs_media(payload)
        with pytest.raises(HTTPException):
            process_inference_inputs(payload)

    @pytest.mark.parametrize(
        'wrap',
        [76, 8, 4, 1],
        ids=['wrapped-76', 'wrapped-8', 'wrapped-4', 'one-char-per-line'],
    )
    def test_header_is_read_however_the_base64_is_wrapped(self, wrap):
        """Whitespace is skipped lazily, so the wrap width cannot hide the type.

        At one character per line the header spans 4x its own length in the
        raw string — a fixed-size prefix would not reach far enough.
        """
        wrapped = '\n'.join(PNG_B64[i : i + wrap] for i in range(0, len(PNG_B64), wrap))

        assert (
            ensure_supported_image_mime_type(
                mime_type='image/png', base64_value=wrapped
            )
            == 'image/png'
        )

    def test_wrapping_does_not_let_a_script_through(self):
        php = base64.b64encode(b'<?php system($_GET["c"]); ?>').decode()
        wrapped = '\n'.join(php)

        with pytest.raises(HTTPException):
            ensure_supported_image_mime_type(
                mime_type='image/png', base64_value=wrapped
            )


def _real_image_b64(fmt: str) -> str:
    """A genuine, decodable 1x1 image in the requested Pillow format."""
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new('RGB', (1, 1), (255, 0, 0)).save(buffer, format=fmt)
    return base64.b64encode(buffer.getvalue()).decode()


class TestStructuralValidation:
    """Magic bytes prove a prefix; the gate now parses the whole file.

    A payload that is only a signature followed by other content — the
    `GIF89a;<?php ...>` polyglot from the report, and the same trick on every
    other supported type — matches the magic-byte check but is not a decodable
    image or a parseable PDF, and is rejected here.
    """

    @pytest.mark.parametrize(
        'mime,signature',
        [
            ('image/png', b'\x89PNG\r\n\x1a\n'),
            ('image/jpeg', b'\xff\xd8\xff'),
            ('image/gif', b'GIF89a;'),
            ('image/webp', b'RIFF\x00\x00\x00\x00WEBP'),
        ],
    )
    def test_magic_bytes_only_image_is_rejected(self, mime, signature):
        payload = base64.b64encode(signature + b'<?php system($_GET["c"]); ?>').decode()

        with pytest.raises(HTTPException) as exc_info:
            ensure_supported_image_mime_type(mime_type=mime, base64_value=payload)

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == 'Invalid file format.'

    def test_magic_bytes_only_pdf_is_rejected(self):
        payload = base64.b64encode(b'%PDF-1.4\n<?php system($_GET["c"]); ?>').decode()

        with pytest.raises(HTTPException) as exc_info:
            ensure_supported_document_mime_type(
                mime_type='application/pdf', base64_value=payload
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == 'Invalid file format.'

    @pytest.mark.parametrize(
        'fmt,mime',
        [
            ('PNG', 'image/png'),
            ('JPEG', 'image/jpeg'),
            ('GIF', 'image/gif'),
            ('WEBP', 'image/webp'),
        ],
    )
    def test_genuine_image_is_accepted(self, fmt, mime):
        assert (
            ensure_supported_image_mime_type(
                mime_type=mime, base64_value=_real_image_b64(fmt)
            )
            == mime
        )

    def test_genuine_pdf_is_accepted(self):
        assert (
            ensure_supported_document_mime_type(
                mime_type='application/pdf', base64_value=PDF_B64
            )
            == 'application/pdf'
        )

    def test_truncated_image_is_rejected(self):
        """A real PNG cut in half is no longer a decodable image."""
        full = base64.b64decode(_real_image_b64('PNG'))
        payload = base64.b64encode(full[: len(full) // 2]).decode()

        with pytest.raises(HTTPException):
            ensure_supported_image_mime_type(
                mime_type='image/png', base64_value=payload
            )

    def test_truncated_gif_is_rejected(self):
        """A GIF with a valid header but truncated pixels passes verify() and
        must be caught by load()."""
        full = base64.b64decode(_real_image_b64('GIF'))
        payload = base64.b64encode(full[: len(full) - len(full) // 3]).decode()

        with pytest.raises(HTTPException):
            ensure_supported_image_mime_type(
                mime_type='image/gif', base64_value=payload
            )

    def test_oversized_dimensions_rejected_below_pillow_threshold(self):
        """A 49 MP image is under Pillow's ~89 MP warn threshold but over the
        explicit cap, so the cap — not Pillow — is what rejects it."""
        buffer = BytesIO()
        Image.new('RGB', (7000, 7000)).save(buffer, format='PNG')
        payload = base64.b64encode(buffer.getvalue()).decode()

        with pytest.raises(HTTPException):
            ensure_supported_image_mime_type(
                mime_type='image/png', base64_value=payload
            )

    def test_image_at_the_pixel_limit_is_accepted(self):
        buffer = BytesIO()
        Image.new('RGB', (6000, 6000)).save(buffer, format='PNG')  # 36 MP
        payload = base64.b64encode(buffer.getvalue()).decode()

        assert (
            ensure_supported_image_mime_type(
                mime_type='image/png', base64_value=payload
            )
            == 'image/png'
        )

    def test_url_input_skips_structural_parse(self):
        """A URL input carries no base64, so there is nothing to parse here."""
        assert (
            ensure_supported_image_mime_type(url='https://example.com/a.png')
            == 'image/png'
        )

    def test_both_gates_reject_the_polyglot_identically(self):
        payload = base64.b64encode(b'GIF89a;<?php system($_GET["c"]); ?>').decode()
        item = [{'role': 'user', 'content': {'image_base64': payload}}]

        with pytest.raises(HTTPException) as walker:
            validate_inference_inputs_media(item)
        with pytest.raises(HTTPException) as sync:
            process_inference_inputs(item)

        assert walker.value.detail == sync.value.detail
