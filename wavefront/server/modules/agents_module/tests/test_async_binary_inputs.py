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


class TestStoredObjectNaming:
    """The stored key's extension decides how a web server treats the object.

    VAPT finding: `file_name` went into the key verbatim, so a caller chose the
    extension — `shell.php`. It now comes from the validated mime type, and the
    caller's name survives only as a sanitised stem.
    """

    def test_caller_cannot_choose_the_extension(self, service):
        inputs = [
            {
                'role': 'user',
                'content': {
                    'image_base64': PNG_B64,
                    'mime_type': 'image/png',
                    'file_name': 'shell.php',
                },
            }
        ]

        service.pre_save_binary_inputs(inputs, 'p/')
        key = service.cloud_storage.save_small_file.call_args.kwargs['key']

        assert key.endswith('.png')
        assert '.php' not in key

    @pytest.mark.parametrize(
        'file_name',
        ['../../../etc/passwd', '..\\..\\win.ini', 'a/b/c.png', 'x.html', 'y.svg'],
    )
    def test_separators_and_markup_extensions_do_not_survive(self, service, file_name):
        inputs = [
            {
                'role': 'user',
                'content': {
                    'image_base64': PNG_B64,
                    'mime_type': 'image/png',
                    'file_name': file_name,
                },
            }
        ]

        service.pre_save_binary_inputs(inputs, 'p/')
        key = service.cloud_storage.save_small_file.call_args.kwargs['key']

        assert key.startswith('p/inputs/')
        assert '..' not in key
        assert key.count('/') == 2
        assert key.endswith('.png')

    def test_original_name_is_still_recorded(self, service):
        """Sanitising the key must not lose what the user called the file."""
        inputs = [
            {
                'role': 'user',
                'content': {
                    'image_base64': PNG_B64,
                    'mime_type': 'image/png',
                    'file_name': 'holiday.png',
                },
            }
        ]

        _, stored = service.pre_save_binary_inputs(inputs, 'p/')

        assert stored[0]['file_name'] == 'holiday.png'

    def test_content_type_is_set_from_the_validated_mime(self, service):
        inputs = [
            {
                'role': 'user',
                'content': {'image_base64': PNG_B64, 'mime_type': 'image/png'},
            }
        ]

        service.pre_save_binary_inputs(inputs, 'p/')
        kwargs = service.cloud_storage.save_small_file.call_args.kwargs

        assert kwargs['content_type'] == 'image/png'

    def test_unsupported_mime_is_stored_as_an_opaque_download(self, service):
        """Never echo an arbitrary caller string back as the served type."""
        inputs = [
            {
                'role': 'user',
                'content': {'image_base64': PNG_B64, 'mime_type': 'text/html'},
            }
        ]

        service.pre_save_binary_inputs(inputs, 'p/')
        kwargs = service.cloud_storage.save_small_file.call_args.kwargs

        assert kwargs['content_type'] == 'application/octet-stream'

    @pytest.mark.parametrize(
        'mime_type', ['image/svg+xml', 'text/html', 'text/csv', 'nonsense', None]
    )
    def test_unsupported_mime_never_earns_a_real_extension(self, service, mime_type):
        """_MIME_TO_EXT is wider than the gate; it must not widen the key too.

        It still maps image/svg+xml to .svg, which is served inline. The gate
        blocks that type today, so this pins the second line of defence rather
        than a live hole.
        """
        content = {'image_base64': PNG_B64}
        if mime_type is not None:
            content['mime_type'] = mime_type

        service.pre_save_binary_inputs([{'role': 'user', 'content': content}], 'p/')
        key = service.cloud_storage.save_small_file.call_args.kwargs['key']

        assert key.endswith('.bin')

    def test_mime_resolved_from_file_name_when_not_declared(self, service):
        """The gate accepts photo.png with no mime_type; storage must agree.

        Resolving the extension only in the gate stored a valid image as an
        unnamed .bin octet-stream, which the UI cannot render from the
        presigned input_files URL.
        """
        inputs = [
            {
                'role': 'user',
                'content': {'image_base64': PNG_B64, 'file_name': 'photo.png'},
            }
        ]

        service.pre_save_binary_inputs(inputs, 'p/')
        kwargs = service.cloud_storage.save_small_file.call_args.kwargs

        assert kwargs['key'] == 'p/inputs/0_photo.png'
        assert kwargs['content_type'] == 'image/png'

    def test_unresolvable_mime_still_falls_back_to_bin(self, service):
        """The file-name fallback must not become a way to name the extension."""
        inputs = [
            {
                'role': 'user',
                'content': {'image_base64': PNG_B64, 'file_name': 'payload.php'},
            }
        ]

        service.pre_save_binary_inputs(inputs, 'p/')
        kwargs = service.cloud_storage.save_small_file.call_args.kwargs

        assert kwargs['key'] == 'p/inputs/0_payload.bin'
        assert kwargs['content_type'] == 'application/octet-stream'
