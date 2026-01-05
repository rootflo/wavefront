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

    def test_image_message_invalid_base64(self):
        """Test that plain base64 (non-data URL) is processed correctly"""
        image_input = {
            'role': 'user',
            'content': {'image_base64': 'invalid_base64_data'},
        }

        inputs = [image_input]

        # The pattern won't match, so it falls back to else branch
        # and uses the provided image_base64 and mime_type (None) directly
        result = process_inference_inputs(inputs)
        assert len(result) == 1
        assert isinstance(result[0], UserMessage)
        assert isinstance(result[0].content, ImageMessageContent)
        assert result[0].content.base64 == 'invalid_base64_data'
        assert result[0].content.mime_type is None

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

    def test_document_message_txt(self):
        """Test processing DocumentMessage with TXT type"""
        # Encode bytes to base64 string as expected by implementation
        document_base64_str = base64.b64encode(b'fake_txt_content').decode('utf-8')
        doc_input = {
            'role': 'user',
            'content': {
                'document_base64': document_base64_str,
                'mime_type': 'text/plain',
            },
        }

        inputs = [doc_input]
        result = process_inference_inputs(inputs)

        assert len(result) == 1
        assert isinstance(result[0], UserMessage)
        assert isinstance(result[0].content, DocumentMessageContent)
        assert result[0].content.mime_type == 'text/plain'
        # base64 field should contain base64-encoded string
        assert result[0].content.base64 == document_base64_str

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
        """Test image message with malformed data URL - should fall back to else branch"""
        image_input = {
            'role': 'user',
            'content': {'image_base64': 'data:invalid_format'},
        }

        inputs = [image_input]

        # The pattern won't match, so it falls back to else branch
        # and uses the provided image_base64 and mime_type (None) directly
        result = process_inference_inputs(inputs)
        assert len(result) == 1
        assert isinstance(result[0], UserMessage)
        assert isinstance(result[0].content, ImageMessageContent)
        assert result[0].content.base64 == 'data:invalid_format'
        assert result[0].content.mime_type is None

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
                'image_base64': f'data:image/svg+xml;base64,{simple_png_b64}',
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
        assert result[1].content.mime_type == 'image/svg+xml'
        assert result[1].content.base64 == simple_png_b64
        assert isinstance(result[2], UserMessage)
        assert isinstance(result[2].content, TextMessageContent)
