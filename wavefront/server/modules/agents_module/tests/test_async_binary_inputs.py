"""Tests for AsyncAgenticExecutionService.pre_save_binary_inputs

This runs on the request path of the async endpoints: it pulls binary payloads
out of the request, uploads them to cloud storage, and replaces them with a
reference the worker later rehydrates.
"""

import base64
from unittest.mock import MagicMock

import pytest

from agents_module.services.async_agentic_execution_service import (
    AsyncAgenticExecutionService,
)

PDF_BYTES = b'%PDF-1.4 fake'
PDF_B64 = base64.b64encode(PDF_BYTES).decode('utf-8')
PNG_BYTES = b'\x89PNG\r\n\x1a\n fake'
PNG_B64 = base64.b64encode(PNG_BYTES).decode('utf-8')


@pytest.fixture
def service():
    return AsyncAgenticExecutionService(
        async_agentic_execution_repository=MagicMock(),
        cloud_storage_manager=MagicMock(),
        cache_manager=MagicMock(),
        executions_bucket='test-bucket',
    )


def saved_bytes(service):
    """The bytes handed to cloud storage on the most recent save"""
    return service.cloud_storage.save_small_file.call_args.kwargs['file_content']


class TestDataUrlStripping:
    """A `data:` prefix must come off before the base64 is decoded"""

    def test_document_data_url_is_stripped(self, service):
        inputs = [
            {
                'role': 'user',
                'content': {
                    'document_base64': f'data:application/pdf;base64,{PDF_B64}'
                },
            }
        ]

        clean, stored = service.pre_save_binary_inputs(inputs, 'prefix/')

        assert saved_bytes(service) == PDF_BYTES
        assert stored[0]['mime_type'] == 'application/pdf'
        assert clean[0]['stored'] is True

    def test_image_data_url_is_stripped(self, service):
        inputs = [
            {
                'role': 'user',
                'content': {'image_base64': f'data:image/png;base64,{PNG_B64}'},
            }
        ]

        _, stored = service.pre_save_binary_inputs(inputs, 'prefix/')

        assert saved_bytes(service) == PNG_BYTES
        assert stored[0]['mime_type'] == 'image/png'

    def test_plain_base64_document_unchanged(self, service):
        inputs = [
            {
                'role': 'user',
                'content': {
                    'document_base64': PDF_B64,
                    'mime_type': 'application/pdf',
                },
            }
        ]

        _, stored = service.pre_save_binary_inputs(inputs, 'prefix/')

        assert saved_bytes(service) == PDF_BYTES
        assert stored[0]['mime_type'] == 'application/pdf'

    def test_explicit_mime_type_wins_over_data_url(self, service):
        inputs = [
            {
                'role': 'user',
                'content': {
                    'image_base64': f'data:image/gif;base64,{PNG_B64}',
                    'mime_type': 'image/png',
                },
            }
        ]

        _, stored = service.pre_save_binary_inputs(inputs, 'prefix/')

        assert stored[0]['mime_type'] == 'image/png'

    def test_data_url_mime_is_normalized(self, service):
        inputs = [
            {
                'role': 'user',
                'content': {'image_base64': f'data:image/jpg;base64,{PNG_B64}'},
            }
        ]

        _, stored = service.pre_save_binary_inputs(inputs, 'prefix/')

        assert stored[0]['mime_type'] == 'image/jpeg'

    def test_invalid_base64_still_raises(self, service):
        inputs = [
            {'role': 'user', 'content': {'document_base64': 'not valid base64!!'}}
        ]

        with pytest.raises(ValueError) as exc_info:
            service.pre_save_binary_inputs(inputs, 'prefix/')

        assert 'Invalid base64 data' in str(exc_info.value)


class TestPassThrough:
    """Non-binary entries are left alone"""

    def test_string_input(self, service):
        clean, stored = service.pre_save_binary_inputs('hello', 'prefix/')

        assert clean == [{'role': 'user', 'content': 'hello'}]
        assert stored == []

    def test_text_and_assistant_messages(self, service):
        inputs = [
            {'role': 'user', 'content': 'hello'},
            {'role': 'assistant', 'content': 'hi'},
        ]

        clean, stored = service.pre_save_binary_inputs(inputs, 'prefix/')

        assert clean == inputs
        assert stored == []
        service.cloud_storage.save_small_file.assert_not_called()
