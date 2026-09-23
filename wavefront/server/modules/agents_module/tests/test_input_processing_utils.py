"""
Tests for input_processing_utils module
"""

import base64
import pytest
from unittest.mock import patch
from fastapi import HTTPException
from flo_ai import (
    ImageMessageContent,
    DocumentMessageContent,
    UserMessage,
    TextMessageContent,
    AssistantMessage,
)

from agents_module.utils.input_processing_utils import (
    process_inference_inputs,
    is_image_message,
    is_doc_message,
)


class TestProcessInferenceInputs:
    """Test cases for process_inference_inputs function"""

    def test_string_input_returns_user_message(self):
        """Test that string input is converted to UserMessage"""
        input_str = 'This is a test string'
        result = process_inference_inputs(input_str)
        assert isinstance(result, UserMessage)
        assert result.role == 'user'
        assert isinstance(result.content, str)
        assert result.content == input_str

    def test_empty_string_input(self):
        """Test that empty string input is converted to UserMessage"""
        input_str = ''
        result = process_inference_inputs(input_str)
        assert isinstance(result, UserMessage)
        assert result.role == 'user'
        assert isinstance(result.content, str)
        assert result.content == input_str

    def test_empty_list_input(self):
        """Test that empty list input returns empty list"""
        result = process_inference_inputs([])
        assert result == []

    def test_list_with_string_only(self):
        """Test list containing only string items - should raise error as strings need role"""
        inputs = ['Hello', 'World', 'Test']
        # The function expects dicts with 'role' field, so strings in list will raise AttributeError
        with pytest.raises(AttributeError):
            process_inference_inputs(inputs)

    def test_image_message_with_data_url(self):
        """Test processing ImageMessage with data URL format"""
        # Create a simple 1x1 pixel PNG in base64
        simple_png_b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='

        image_input = {
            'role': 'user',
            'content': {
                'image_base64': f'data:image/png;base64,{simple_png_b64}',
            },
        }

        inputs = [image_input]
        result = process_inference_inputs(inputs)

        assert len(result) == 1
        assert isinstance(result[0], UserMessage)
        assert isinstance(result[0].content, ImageMessageContent)
        assert result[0].content.mime_type == 'image/png'
        # base64 field should contain only the base64 part (without data URL prefix)
        assert result[0].content.base64 == simple_png_b64
        assert isinstance(result[0].content.base64, str)

    def test_image_message_with_plain_base64(self):
        """Test processing ImageMessage with plain base64 (no data URL prefix)"""
        simple_png_b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='

        image_input = {
            'role': 'user',
            'content': {
                'image_base64': simple_png_b64,
                'mime_type': 'image/png',
            },
        }

        inputs = [image_input]
        result = process_inference_inputs(inputs)

        assert len(result) == 1
        assert isinstance(result[0], UserMessage)
        assert isinstance(result[0].content, ImageMessageContent)
        assert result[0].content.mime_type == 'image/png'
        # base64 field should contain the provided base64 string
        assert result[0].content.base64 == simple_png_b64
        assert isinstance(result[0].content.base64, str)

    def test_image_message_without_resolvable_mime_type(self):
        """Test that an image with no determinable mime type is rejected

        The provider needs the mime type to build the image data URL, so
        letting this through only defers the failure into the LLM call.
        """
        image_input = {
            'role': 'user',
            'content': {'image_base64': 'invalid_base64_data'},
        }

        with pytest.raises(HTTPException) as exc_info:
            process_inference_inputs([image_input])

        assert exc_info.value.status_code == 400
        assert 'Could not determine the mime type' in str(exc_info.value.detail)

    def test_image_message_with_none_base64(self):
        """Test that None image_base64 raises HTTPException"""
        image_input = {
            'role': 'user',
            'content': {'image_base64': None},
        }

        inputs = [image_input]

        # re.match will raise TypeError when given None, which will be caught
        # and re-raised as HTTPException
        with pytest.raises(HTTPException) as exc_info:
            process_inference_inputs(inputs)

        assert exc_info.value.status_code == 400
        assert 'Invalid base64 image data' in str(exc_info.value.detail)

    def test_document_message_pdf(self):
        """Test processing DocumentMessage with PDF type"""
        # Encode bytes to base64 string as expected by implementation
        document_base64_str = base64.b64encode(b'fake_pdf_content').decode('utf-8')
        doc_input = {
            'role': 'user',
            'content': {
                'document_base64': document_base64_str,
                'mime_type': 'application/pdf',
            },
        }

        inputs = [doc_input]
        result = process_inference_inputs(inputs)

        assert len(result) == 1
        assert isinstance(result[0], UserMessage)
        assert isinstance(result[0].content, DocumentMessageContent)
        assert result[0].content.mime_type == 'application/pdf'
        # base64 field should contain base64-encoded string
        assert result[0].content.base64 == document_base64_str

    def test_document_message_txt_becomes_text_content(self):
        """A text/plain document is extracted rather than rejected.

        This used to assert a 400: the formatter only rasterizes PDFs, so
        anything else failed. Extractable types now never reach the formatter —
        they are converted to a TextMessageContent at the boundary.
        """
        document_base64_str = base64.b64encode(b'quarterly notes').decode('utf-8')
        doc_input = {
            'role': 'user',
            'content': {
                'document_base64': document_base64_str,
                'mime_type': 'text/plain',
                'file_name': 'notes.txt',
            },
        }

        result = process_inference_inputs([doc_input])

        assert len(result) == 1
        assert isinstance(result[0].content, TextMessageContent)
        assert 'quarterly notes' in result[0].content.text
        assert 'notes.txt' in result[0].content.text

    def test_document_message_csv_becomes_text_content(self):
        document_base64_str = base64.b64encode(b'region,revenue\nEast,1200\n').decode(
            'utf-8'
        )
        doc_input = {
            'role': 'user',
            'content': {
                'document_base64': document_base64_str,
                'mime_type': 'text/csv',
                'file_name': 'q3.csv',
            },
        }

        result = process_inference_inputs([doc_input])

        assert isinstance(result[0].content, TextMessageContent)
        assert 'East,1200' in result[0].content.text

    def test_pdf_still_becomes_document_content(self):
        """The native path must be untouched by the extraction branch."""
        document_base64_str = base64.b64encode(b'%PDF-1.4 fake').decode('utf-8')
        doc_input = {
            'role': 'user',
            'content': {
                'document_base64': document_base64_str,
                'mime_type': 'application/pdf',
            },
        }

        result = process_inference_inputs([doc_input])

        assert isinstance(result[0].content, DocumentMessageContent)

    def test_unreadable_extractable_document_is_a_400(self):
        """A .docx that is not a zip fails at the boundary, not mid-run."""
        document_base64_str = base64.b64encode(b'definitely not a zip').decode('utf-8')
        doc_input = {
            'role': 'user',
            'content': {
                'document_base64': document_base64_str,
                'mime_type': (
                    'application/vnd.openxmlformats-officedocument'
                    '.wordprocessingml.document'
                ),
                'file_name': 'broken.docx',
            },
        }

        with pytest.raises(HTTPException) as exc_info:
            process_inference_inputs([doc_input])

        assert exc_info.value.status_code == 400
        assert 'index 0' in str(exc_info.value.detail)

    def test_extractable_document_url_without_bytes_is_rejected(self):
        """Nothing server-side fetches remote documents."""
        doc_input = {
            'role': 'user',
            'content': {
                'document_url': 'https://example.com/report.docx',
                'mime_type': (
                    'application/vnd.openxmlformats-officedocument'
                    '.wordprocessingml.document'
                ),
            },
        }

        with pytest.raises(HTTPException) as exc_info:
            process_inference_inputs([doc_input])

        assert exc_info.value.status_code == 400
        assert 'document_url' in str(exc_info.value.detail)

    def test_document_message_default_type(self):
        """Test DocumentMessage processing"""
        document_base64_str = base64.b64encode(b'content').decode('utf-8')
        doc_input = {
            'role': 'user',
            'content': {'document_base64': document_base64_str},
        }

        inputs = [doc_input]
        result = process_inference_inputs(inputs)

        assert len(result) == 1
        assert isinstance(result[0], UserMessage)
        assert isinstance(result[0].content, DocumentMessageContent)

    def test_mixed_inputs(self):
        """Test processing mixed list with text, images, and documents"""
        simple_png_b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
        document_base64_str = base64.b64encode(b'pdf_content').decode('utf-8')

        inputs = [
            {'role': 'user', 'content': 'Text input'},
            {
                'role': 'user',
                'content': {'image_base64': f'data:image/png;base64,{simple_png_b64}'},
            },
            {'role': 'user', 'content': 'Another text input'},
            {
                'role': 'user',
                'content': {'document_base64': document_base64_str},
            },
        ]

        result = process_inference_inputs(inputs)

        assert len(result) == 4
        assert isinstance(result[0], UserMessage)
        assert isinstance(result[0].content, TextMessageContent)
        assert result[0].content.text == 'Text input'
        assert isinstance(result[1], UserMessage)
        assert isinstance(result[1].content, ImageMessageContent)
        assert result[1].content.mime_type == 'image/png'
        assert result[1].content.base64 == simple_png_b64
        assert isinstance(result[2], UserMessage)
        assert isinstance(result[2].content, TextMessageContent)
        assert result[2].content.text == 'Another text input'
        assert isinstance(result[3], UserMessage)
        assert isinstance(result[3].content, DocumentMessageContent)

    def test_assistant_message(self):
        """Test processing AssistantMessage"""
        assistant_input = {
            'role': 'assistant',
            'content': 'This is an assistant message',
        }

        inputs = [assistant_input]
        result = process_inference_inputs(inputs)

        assert len(result) == 1
        assert isinstance(result[0], AssistantMessage)
        assert result[0].content == 'This is an assistant message'
        assert result[0].role == 'assistant'

    @patch('agents_module.utils.input_processing_utils.logger')
    def test_image_processing_error_logging(self, mock_logger):
        """Test that image processing errors are logged"""
        image_input = {
            'role': 'user',
            'content': {'image_base64': None},
        }

        inputs = [image_input]

        with pytest.raises(HTTPException):
            process_inference_inputs(inputs)

        mock_logger.error.assert_called_once()
        assert 'Error processing ImageMessage base64' in str(
            mock_logger.error.call_args
        )


class TestFileNamePropagation:
    """Test cases for carrying the original file_name onto media content"""

    def test_image_data_url_carries_file_name(self):
        """Test that file_name survives the data URL branch"""
        simple_png_b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='

        inputs = [
            {
                'role': 'user',
                'content': {
                    'image_base64': f'data:image/png;base64,{simple_png_b64}',
                    'file_name': 'photo.png',
                },
            }
        ]

        result = process_inference_inputs(inputs)

        # Exactly one message - the file name rides on the content, it is not
        # injected as an extra text message
        assert len(result) == 1
        assert isinstance(result[0].content, ImageMessageContent)
        assert result[0].content.file_name == 'photo.png'

    def test_image_plain_base64_carries_file_name(self):
        """Test that file_name survives the plain base64 branch"""
        simple_png_b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='

        inputs = [
            {
                'role': 'user',
                'content': {
                    'image_base64': simple_png_b64,
                    'mime_type': 'image/png',
                    'file_name': 'photo.png',
                },
            }
        ]

        result = process_inference_inputs(inputs)

        assert len(result) == 1
        assert isinstance(result[0].content, ImageMessageContent)
        assert result[0].content.file_name == 'photo.png'

    def test_document_data_url_prefix_is_stripped(self):
        """Test that a document sent as a data URL has the prefix removed

        Every provider feeds `.base64` straight to a decoder, so leaving the
        `data:...;base64,` prefix on produces garbage bytes instead of an error.
        """
        document_base64_str = base64.b64encode(b'%PDF-1.4 fake').decode('utf-8')

        inputs = [
            {
                'role': 'user',
                'content': {
                    'document_base64': (
                        f'data:application/pdf;base64,{document_base64_str}'
                    )
                },
            }
        ]

        result = process_inference_inputs(inputs)

        assert len(result) == 1
        assert isinstance(result[0].content, DocumentMessageContent)
        assert result[0].content.base64 == document_base64_str
        assert result[0].content.mime_type == 'application/pdf'
        # The stripped payload must survive a strict decode
        assert base64.b64decode(result[0].content.base64, validate=True) == (
            b'%PDF-1.4 fake'
        )

    def test_document_data_url_with_unsupported_mime_rejected(self):
        """Test that the mime in a document data URL is still gated

        Uses .pptx: this asserted on text/csv until CSV became an extractable
        type, and the point of the test is the data-URL mime being read at all.
        """
        document_base64_str = base64.b64encode(b'fake').decode('utf-8')
        pptx_mime = (
            'application/vnd.openxmlformats-officedocument'
            '.presentationml.presentation'
        )

        inputs = [
            {
                'role': 'user',
                'content': {
                    'document_base64': (
                        f'data:{pptx_mime};base64,{document_base64_str}'
                    )
                },
            }
        ]

        with pytest.raises(HTTPException) as exc_info:
            process_inference_inputs(inputs)

        assert f'Unsupported document type `{pptx_mime}`' in str(exc_info.value.detail)

    def test_plain_document_base64_untouched(self):
        """Test that a document with no data URL prefix is passed through as-is"""
        document_base64_str = base64.b64encode(b'%PDF-1.4 fake').decode('utf-8')

        inputs = [
            {
                'role': 'user',
                'content': {
                    'document_base64': document_base64_str,
                    'mime_type': 'application/pdf',
                },
            }
        ]

        result = process_inference_inputs(inputs)

        assert result[0].content.base64 == document_base64_str

    def test_document_carries_file_name(self):
        """Test that file_name is set on DocumentMessageContent"""
        document_base64_str = base64.b64encode(b'fake_pdf_content').decode('utf-8')

        inputs = [
            {
                'role': 'user',
                'content': {
                    'document_base64': document_base64_str,
                    'mime_type': 'application/pdf',
                    'file_name': 'invoice.pdf',
                },
            }
        ]

        result = process_inference_inputs(inputs)

        assert len(result) == 1
        assert isinstance(result[0].content, DocumentMessageContent)
        assert result[0].content.file_name == 'invoice.pdf'

    def test_media_without_file_name_defaults_to_none(self):
        """Test that omitting file_name leaves it None on image and document"""
        simple_png_b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
        document_base64_str = base64.b64encode(b'fake_pdf_content').decode('utf-8')

        inputs = [
            {
                'role': 'user',
                'content': {'image_base64': f'data:image/png;base64,{simple_png_b64}'},
            },
            {
                'role': 'user',
                'content': {
                    'document_base64': document_base64_str,
                    'mime_type': 'application/pdf',
                },
            },
        ]

        result = process_inference_inputs(inputs)

        assert len(result) == 2
        assert result[0].content.file_name is None
        assert result[1].content.file_name is None


class TestIsImageMessage:
    """Test cases for is_image_message function"""

    def test_image_url_detected(self):
        """Test that image_url key is detected"""
        input_item = {'image_url': 'https://example.com/image.png'}
        assert is_image_message(input_item) is True

    def test_image_base64_detected(self):
        """Test that image_base64 key is detected"""
        input_item = {'image_base64': 'base64_data'}
        assert is_image_message(input_item) is True

    def test_image_bytes_detected(self):
        """Test that image_bytes key is detected"""
        input_item = {'image_bytes': b'image_data'}
        assert is_image_message(input_item) is True

    def test_image_file_path_detected(self):
        """Test that image_file_path key is detected"""
        input_item = {'image_file_path': '/path/to/image.png'}
        assert is_image_message(input_item) is True

    def test_multiple_image_keys(self):
        """Test that multiple image keys are detected"""
        input_item = {
            'image_url': 'https://example.com/image.png',
            'image_base64': 'base64_data',
        }
        assert is_image_message(input_item) is True

    def test_non_image_message(self):
        """Test that non-image messages are not detected"""
        input_item = {'text': 'This is just text'}
        assert is_image_message(input_item) is False

    def test_empty_dict(self):
        """Test that empty dict is not detected as image message"""
        input_item = {}
        assert is_image_message(input_item) is False


class TestIsDocMessage:
    """Test cases for is_doc_message function"""

    def test_document_url_detected(self):
        """Test that document_url key is detected"""
        input_item = {'document_url': 'https://example.com/doc.pdf'}
        assert is_doc_message(input_item) is True

    def test_document_base64_detected(self):
        """Test that document_base64 key is detected"""
        input_item = {'document_base64': 'base64_data'}
        assert is_doc_message(input_item) is True

    def test_document_bytes_detected(self):
        """Test that document_bytes key is detected"""
        input_item = {'document_bytes': b'document_data'}
        assert is_doc_message(input_item) is True

    def test_document_file_path_detected(self):
        """Test that document_file_path key is detected"""
        input_item = {'document_file_path': '/path/to/doc.pdf'}
        assert is_doc_message(input_item) is True

    def test_multiple_document_keys(self):
        """Test that multiple document keys are detected"""
        input_item = {
            'document_url': 'https://example.com/doc.pdf',
            'document_base64': 'base64_data',
        }
        assert is_doc_message(input_item) is True

    def test_non_document_message(self):
        """Test that non-document messages are not detected"""
        input_item = {'text': 'This is just text'}
        assert is_doc_message(input_item) is False

    def test_empty_dict(self):
        """Test that empty dict is not detected as document message"""
        input_item = {}
        assert is_doc_message(input_item) is False


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_none_input(self):
        """Test that None input is handled gracefully"""
        with pytest.raises(TypeError):
            process_inference_inputs(None)

    def test_integer_input(self):
        """Test that integer input raises appropriate error"""
        with pytest.raises(TypeError):
            process_inference_inputs(123)

    def test_dict_input_not_list_or_string(self):
        """Test that dict input (not list or string) raises error"""
        # The function expects either str or List, so a dict should raise TypeError
        with pytest.raises((TypeError, AttributeError)):
            process_inference_inputs({'key': 'value'})

    def test_nested_list_input(self):
        """Test that nested lists are handled"""
        inputs = [
            {'role': 'user', 'content': 'nested'},
            {'role': 'user', 'content': 'string'},
        ]
        result = process_inference_inputs(inputs)
        assert len(result) == 2
        assert isinstance(result[0], UserMessage)
        assert isinstance(result[1], UserMessage)

    def test_image_message_with_malformed_data_url(self):
        """Test malformed data URL - no mime can be resolved, so it is rejected"""
        image_input = {
            'role': 'user',
            'content': {'image_base64': 'data:invalid_format'},
        }

        with pytest.raises(HTTPException) as exc_info:
            process_inference_inputs([image_input])

        assert exc_info.value.status_code == 400
        assert 'Could not determine the mime type' in str(exc_info.value.detail)

    def test_document_message_with_none_values(self):
        """Test document message with None values"""
        doc_input = {
            'role': 'user',
            'content': {
                'document_base64': None,
                'mime_type': None,
            },
        }

        inputs = [doc_input]
        result = process_inference_inputs(inputs)

        assert len(result) == 1
        assert isinstance(result[0], UserMessage)
        assert isinstance(result[0].content, DocumentMessageContent)

    def test_image_message_image_and_string(self):
        """Test processing ImageMessage with text messages"""
        simple_png_b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='

        image_input = {
            'role': 'user',
            'content': {
                'image_base64': f'data:image/png;base64,{simple_png_b64}',
            },
        }

        inputs = [
            {'role': 'user', 'content': 'Validation Cruel'},
            image_input,
            {'role': 'user', 'content': 'Validation Cruel'},
        ]
        result = process_inference_inputs(inputs)

        assert len(result) == 3
        assert isinstance(result[0], UserMessage)
        assert isinstance(result[0].content, TextMessageContent)
        assert isinstance(result[1], UserMessage)
        assert isinstance(result[1].content, ImageMessageContent)
        assert result[1].content.mime_type == 'image/png'
        assert result[1].content.base64 == simple_png_b64
        assert isinstance(result[2], UserMessage)
        assert isinstance(result[2].content, TextMessageContent)

    def test_svg_image_rejected(self):
        """Test that SVG is rejected - Azure vision deployments cannot read it"""
        simple_png_b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='

        image_input = {
            'role': 'user',
            'content': {
                'image_base64': f'data:image/svg+xml;base64,{simple_png_b64}',
            },
        }

        with pytest.raises(HTTPException) as exc_info:
            process_inference_inputs([image_input])

        assert exc_info.value.status_code == 400
        assert 'Unsupported image type `image/svg+xml`' in str(exc_info.value.detail)
