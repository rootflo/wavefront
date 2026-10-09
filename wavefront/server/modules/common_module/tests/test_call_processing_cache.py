"""Tests for CallProcessingCacheInvalidator and its wiring in CommonContainer."""

import json
from uuid import UUID

import httpx
import pytest

from common_module.call_processing_cache import CallProcessingCacheInvalidator
from common_module.common_container import CommonContainer

CONFIG_ID = UUID('11111111-2222-3333-4444-555555555555')


@pytest.fixture
def transport(monkeypatch):
    """Route every httpx.AsyncClient through a recording MockTransport."""

    class Recorder:
        requests: list[httpx.Request] = []
        handler = staticmethod(lambda request: httpx.Response(200, json={}))

    def dispatch(request: httpx.Request) -> httpx.Response:
        Recorder.requests = [*Recorder.requests, request]
        return Recorder.handler(request)

    real_client = httpx.AsyncClient

    def make_client(*args, **kwargs):
        kwargs['transport'] = httpx.MockTransport(dispatch)
        return real_client(*args, **kwargs)

    Recorder.requests = []
    monkeypatch.setattr(httpx, 'AsyncClient', make_client)
    return Recorder


def make_invalidator(**overrides) -> CallProcessingCacheInvalidator:
    params = {
        'call_processing_base_url': 'http://call-processing:8002',
        'passthrough_secret': 's3cret',
    }
    params.update(overrides)
    return CallProcessingCacheInvalidator(**params)


class TestInvalidate:
    async def test_posts_config_to_call_processing(self, transport):
        result = await make_invalidator().invalidate('tts_config', CONFIG_ID, 'create')

        assert result is True
        (request,) = transport.requests
        assert request.method == 'POST'
        assert str(request.url) == 'http://call-processing:8002/api/cache/invalidate'
        assert request.headers['X-Passthrough'] == 's3cret'
        assert json.loads(request.content) == {
            'config_type': 'tts_config',
            'config_id': str(CONFIG_ID),
        }

    async def test_string_ids_are_sent_unchanged(self, transport):
        await make_invalidator().invalidate('inbound_number', '+15551234567')

        (request,) = transport.requests
        assert json.loads(request.content)['config_id'] == '+15551234567'

    async def test_trailing_slash_on_base_url_is_ignored(self, transport):
        invalidator = make_invalidator(call_processing_base_url='http://cp:8002/')
        await invalidator.invalidate('stt_config', CONFIG_ID)

        assert str(transport.requests[0].url) == 'http://cp:8002/api/cache/invalidate'

    @pytest.mark.parametrize('status', [200, 201])
    async def test_success_statuses(self, transport, status):
        transport.handler = lambda request: httpx.Response(status)

        assert await make_invalidator().invalidate('stt_config', CONFIG_ID) is True

    @pytest.mark.parametrize('status', [204, 400, 401, 500])
    async def test_other_statuses_are_failures(self, transport, status):
        transport.handler = lambda request: httpx.Response(status, text='nope')

        assert await make_invalidator().invalidate('stt_config', CONFIG_ID) is False


class TestNotConfigured:
    @pytest.mark.parametrize(
        'overrides',
        [
            {'call_processing_base_url': None},
            {'call_processing_base_url': ''},
        ],
    )
    async def test_skipped_without_base_url(self, transport, overrides):
        result = await make_invalidator(**overrides).invalidate(
            'voice_agent', CONFIG_ID
        )

        assert result is False
        assert transport.requests == []

    @pytest.mark.parametrize('secret', [None, ''])
    async def test_still_sends_without_passthrough_secret(self, transport, secret):
        result = await make_invalidator(passthrough_secret=secret).invalidate(
            'voice_agent', CONFIG_ID
        )

        assert result is True
        (request,) = transport.requests
        assert 'X-Passthrough' not in request.headers


class TestNeverRaises:
    @pytest.mark.parametrize(
        'error',
        [
            httpx.ConnectTimeout('timed out'),
            httpx.ConnectError('refused'),
            RuntimeError('boom'),
        ],
    )
    async def test_errors_become_false(self, transport, error):
        def fail(request):
            raise error

        transport.handler = fail

        assert await make_invalidator().invalidate('voice_agent', CONFIG_ID) is False


class TestContainerWiring:
    def test_built_from_runtime_settings(self):
        container = CommonContainer()
        container.config.from_dict(
            {
                'env_config': {
                    'app_env': 'test',
                    'base_url': 'http://localhost:8001',
                    'passthrough_secret': 'abc',
                    'worker_count': '1',
                    'uvicorn_log_level': 'critical',
                },
                'web': {'allowed_origins': 'http://localhost:5173'},
                'voice_agents': {'call_processing_base_url': 'http://cp:9000'},
            }
        )

        invalidator = container.call_processing_cache_invalidator()

        assert invalidator.call_processing_base_url == 'http://cp:9000'
        assert invalidator.passthrough_secret == 'abc'
        assert container.call_processing_cache_invalidator() is invalidator
