import base64

import pytest
from fastapi import HTTPException

from agents_module.utils.input_processing_utils import (
    process_inference_inputs,
    validate_inference_inputs_media,
)
from agents_module.utils.mime_type_utils import (
    SUPPORTED_DOCUMENT_MIME_TYPES,
    SUPPORTED_IMAGE_MIME_TYPES,
    ensure_supported_document_mime_type,
    ensure_supported_image_mime_type,
    normalize_mime_type,
    resolve_mime_type,
    split_data_url,
)

PNG_B64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
PDF_B64 = base64.b64encode(b'%PDF-1.4 fake').decode('utf-8')


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
