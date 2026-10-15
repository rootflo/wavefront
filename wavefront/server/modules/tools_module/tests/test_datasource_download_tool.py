"""datasource_download_file: the agent-facing read side of file storage datasources."""

import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import flo_lib.http as httpx
import pytest

from tools_module.datasources import datasource_api_tools
from tools_module.datasources.provider import DatasourceToolDetailsProvider
from tools_module.floware_api import FlowareApiClient
from tools_module.registry.function_registry import build_function_registry
from tools_module.registry.tool_loader import ToolLoader


@pytest.fixture
def http(monkeypatch):
    """Route every httpx.AsyncClient through a recording MockTransport."""

    class Recorder:
        requests: list[httpx.Request] = []
        reply = staticmethod(lambda request: httpx.Response(200, content=b''))

    def dispatch(request: httpx.Request) -> httpx.Response:
        Recorder.requests = [*Recorder.requests, request]
        return Recorder.reply(request)

    real_client = httpx.AsyncClient

    def make_client(*args, **kwargs):
        kwargs['transport'] = httpx.MockTransport(dispatch)
        return real_client(*args, **kwargs)

    Recorder.requests = []
    monkeypatch.setattr(httpx, 'AsyncClient', make_client)
    return Recorder


def _download():
    registry = build_function_registry(
        FlowareApiClient('http://floware', passthrough_secret='s3cret')
    )
    return registry['datasource_download_file']


def _error(status: int, message: str) -> httpx.Response:
    return httpx.Response(
        status, json={'meta': {'status': 'failure', 'error': message}, 'data': None}
    )


class TestDatasourceDownloadFile:
    async def test_text_file_is_returned_inline(self, http):
        http.reply = lambda request: httpx.Response(
            200, content=b'id,total\n1,10\n', headers={'content-type': 'text/csv'}
        )

        result = json.loads(await _download()('ds 1', 's3://bucket/reports/q1.csv'))

        assert result == {
            'path': 's3://bucket/reports/q1.csv',
            'content_type': 'text/csv',
            'size_bytes': 14,
            'encoding': 'utf-8',
            'content': 'id,total\n1,10\n',
        }

    async def test_request_targets_files_endpoint_with_path_and_auth(self, http):
        await _download()('ds 1', 'reports/q1.csv')

        (request,) = http.requests
        assert request.method == 'GET'
        assert str(request.url).startswith(
            'http://floware/floware/v1/datasources/ds%201/files?'
        )
        assert request.url.params['path'] == 'reports/q1.csv'
        assert request.headers['X-Passthrough'] == 's3cret'

    async def test_binary_file_is_base64(self, http):
        payload = b'\x89PNG\r\n\x1a\n\x00\xff'
        http.reply = lambda request: httpx.Response(
            200, content=payload, headers={'content-type': 'image/png'}
        )

        result = json.loads(await _download()('ds-1', 'img/logo.png'))

        assert result['encoding'] == 'base64'
        assert base64.b64decode(result['content']) == payload
        assert result['size_bytes'] == len(payload)

    async def test_oversized_file_is_refused(self, http, monkeypatch):
        monkeypatch.setattr(datasource_api_tools, 'MAX_DOWNLOAD_BYTES', 4)
        http.reply = lambda request: httpx.Response(200, content=b'12345')

        result = await _download()('ds-1', 'big.bin')

        assert (
            result == "File 'big.bin' is 5 bytes, over the 4-byte limit for this tool"
        )

    async def test_not_found_quotes_server_error(self, http):
        http.reply = lambda request: _error(404, 'File not found: s3://b/missing.txt')

        result = await _download()('ds-1', 'missing.txt')

        assert result == 'File not found: s3://b/missing.txt'

    async def test_not_found_without_envelope_has_fallback(self, http):
        http.reply = lambda request: httpx.Response(404, text='nope')

        result = await _download()('ds-1', 'missing.txt')

        assert result == "File 'missing.txt' not found in datasource 'ds-1'"

    async def test_bad_path_returns_server_error(self, http):
        http.reply = lambda request: _error(400, 'Path escapes the base path')

        result = await _download()('ds-1', '../secret')

        assert result == 'File download failed (400): Path escapes the base path'

    async def test_unreachable_api(self, http):
        def fail(request):
            raise httpx.ConnectError('refused', request=request)

        http.reply = fail

        result = await _download()('ds-1', 'a.txt')

        assert result.startswith("Failed to reach datasource API for 'ds-1'")


class TestDownloadToolRegistration:
    def test_tool_loads_with_path_required(self):
        loader = ToolLoader(
            function_registry=build_function_registry(FlowareApiClient('http://f'))
        )

        metadata = loader.get_tool_metadata('datasource_download_file')
        tool = loader.load_tool('datasource_download_file')

        assert tool is not None
        assert metadata['prefill_values'] == ['datasource_id']
        assert metadata['required'] == ['path']
        assert metadata['datasource_kind'] == 'file_storage'


class TestDatasourceToolDetailsProvider:
    @pytest.fixture
    def provider(self):
        datasources = [
            SimpleNamespace(
                type=ds_type,
                to_dict=lambda ds_type=ds_type: {
                    'id': f'id-{ds_type}',
                    'name': ds_type,
                },
            )
            for ds_type in ('postgresql', 'aws_s3', 'gcs', 'azure_blob_storage')
        ]
        repository = SimpleNamespace(find=AsyncMock(return_value=datasources))
        return DatasourceToolDetailsProvider(repository)

    @staticmethod
    def _metadata(name: str) -> dict:
        return ToolLoader(function_registry={}).get_tool_metadata(name)

    async def test_file_tool_is_offered_for_file_storage_datasources_only(
        self, provider
    ):
        details = await provider.get_tool_details(
            self._metadata('datasource_download_file')
        )

        assert [d.resource_name for d in details] == [
            'aws_s3',
            'gcs',
            'azure_blob_storage',
        ]
        assert details[0].prefilled_value == {'datasource_id': 'id-aws_s3'}

    async def test_sql_tools_skip_file_storage_datasources(self, provider):
        details = await provider.get_tool_details(
            self._metadata('datasource_execute_query')
        )

        assert [d.resource_name for d in details] == ['postgresql']
