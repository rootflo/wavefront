"""trigger_api_service: returns the response body as-is, success or failure; never raises;
optional retries with exponential backoff."""

import json

import flo_lib.http as httpx
import pytest

from tools_module.floware_api import FlowareApiClient
from tools_module.utils import api_service_fn
from tools_module.utils.api_service_fn import (
    execute_api_service_fn,
    max_hold_seconds,
    retry_delays,
)


@pytest.fixture
def http(monkeypatch):
    """Route every httpx.AsyncClient through a recording MockTransport."""

    class Recorder:
        requests: list[httpx.Request] = []
        reply = staticmethod(lambda request: httpx.Response(200, json={}))

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


API = FlowareApiClient('http://f', passthrough_secret='s3cret')


async def call(**kwargs):
    return await execute_api_service_fn(API, 'svc', 'api', **kwargs)


async def test_success_returns_body_as_is(http):
    body = {'meta': {'status': 'success'}, 'data': {'status': 200, 'ok': True}}
    http.reply = lambda r: httpx.Response(200, json=body)
    assert json.loads(await call(quotation_no='Q1')) == body
    sent = json.loads(http.requests[0].content)
    assert sent['payload'] == {'quotation_no': 'Q1'}
    assert sent['api_id'] == 'api'


async def test_success_with_string_or_empty_data(http):
    for body in (
        {'meta': {'status': 'success'}, 'data': 'done'},
        {'meta': {'status': 'success'}, 'data': None},
    ):
        http.reply = lambda r, body=body: httpx.Response(200, json=body)
        assert json.loads(await call()) == body


async def test_http_error_returned_not_raised(http):
    body = {
        'meta': {'status': 'success', 'message': 'Request processed successfully'},
        'data': {'status': 401, 'error': 'UNAUTHORIZED'},
    }
    http.reply = lambda r: httpx.Response(401, json=body)
    assert json.loads(await call()) == body


async def test_floware_error_body_returned_not_raised(http):
    http.reply = lambda r: httpx.Response(404, json={'detail': 'API not found'})
    assert json.loads(await call()) == {'detail': 'API not found'}


async def test_failed_envelope_returned_not_raised(http):
    body = {'meta': {'status': 'failure', 'message': 'pipeline broke'}, 'data': None}
    http.reply = lambda r: httpx.Response(200, json=body)
    assert json.loads(await call()) == body


async def test_unreachable_gives_error_json(http):
    def boom(request):
        raise httpx.ConnectError('refused', request=request)

    http.reply = boom
    out = json.loads(await call())
    assert list(out) == ['error']
    assert 'Failed to reach API service API for svc/api' in out['error']


async def test_non_json_gives_error_json(http):
    http.reply = lambda r: httpx.Response(
        200, content=b'%PDF', headers={'content-type': 'application/pdf'}
    )
    out = json.loads(await call())
    assert list(out) == ['error']
    assert 'application/pdf' in out['error']


async def test_invalid_json_gives_error_json(http):
    http.reply = lambda r: httpx.Response(
        502, content=b'<html>bad gateway</html>', headers={'content-type': 'text/html'}
    )
    out = json.loads(await call())
    assert '502' in out['error']


# --- retries ---------------------------------------------------------------


@pytest.fixture
def sleeps(monkeypatch):
    """Record backoff waits instead of sleeping."""
    waited: list[float] = []

    async def fake_sleep(seconds):
        waited.append(seconds)

    monkeypatch.setattr(api_service_fn.asyncio, 'sleep', fake_sleep)
    return waited


OK_BODY = {'meta': {'status': 'success'}, 'data': {'status': 200}}


def replies(*answers):
    """Answer each request with the next item: a status code, or an exception."""
    queue = list(answers)

    def reply(request):
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        body = OK_BODY if answer == 200 else {'meta': {}, 'data': {'status': answer}}
        return httpx.Response(answer, json=body)

    return reply


def test_retry_delays_double_and_fill_the_window():
    delays = retry_delays(5, 900)
    assert [round(d, 2) for d in delays] == [29.03, 58.06, 116.13, 232.26, 464.52]
    assert round(sum(delays), 6) == 900
    assert retry_delays(0, 900) == []


def test_max_hold_is_window_plus_one_timeout_per_attempt():
    assert max_hold_seconds(5, 900) == 900 + 6 * 60
    assert max_hold_seconds(3, 900) == 900 + 4 * 60


async def test_retries_off_by_default(http, sleeps):
    http.reply = replies(503)
    out = json.loads(await call())
    assert out['data']['status'] == 503
    assert len(http.requests) == 1
    assert sleeps == []


async def test_retries_until_success(http, sleeps):
    http.reply = replies(503, 502, 200)
    out = await call(retry_enabled=True, max_retries=3, retry_window_seconds=70)
    assert json.loads(out) == OK_BODY
    assert len(http.requests) == 3
    assert sleeps == [10, 20]


async def test_gives_up_after_max_retries_with_last_body(http, sleeps):
    http.reply = replies(503, 503, 503)
    out = json.loads(
        await call(retry_enabled=True, max_retries=2, retry_window_seconds=3)
    )
    assert out['data']['status'] == 503
    assert len(http.requests) == 3
    assert sleeps == [1, 2]


async def test_client_errors_are_not_retried(http, sleeps):
    http.reply = replies(401)
    out = json.loads(await call(retry_enabled=True, max_retries=5))
    assert out['data']['status'] == 401
    assert len(http.requests) == 1
    assert sleeps == []


async def test_429_and_408_are_retried(http, sleeps):
    http.reply = replies(429, 408, 200)
    out = await call(retry_enabled=True, max_retries=2, retry_window_seconds=3)
    assert json.loads(out) == OK_BODY
    assert len(http.requests) == 3


async def test_unreachable_is_retried(http, sleeps):
    queue = ['boom', 200]

    def reply(request):
        if queue.pop(0) == 'boom':
            raise httpx.ConnectError('refused', request=request)
        return httpx.Response(200, json=OK_BODY)

    http.reply = reply
    out = await call(retry_enabled=True, max_retries=1, retry_window_seconds=5)
    assert json.loads(out) == OK_BODY
    assert sleeps == [5]


async def test_unreachable_every_time_gives_error_json(http, sleeps):
    def reply(request):
        raise httpx.ConnectError('refused', request=request)

    http.reply = reply
    out = json.loads(
        await call(retry_enabled=True, max_retries=2, retry_window_seconds=3)
    )
    assert list(out) == ['error']
    assert 'refused' in out['error']
    assert len(sleeps) == 2


async def test_yaml_style_strings_are_accepted(http, sleeps):
    http.reply = replies(500, 200)
    out = await call(retry_enabled='true', max_retries='1', retry_window_seconds='60')
    assert json.loads(out) == OK_BODY
    assert sleeps == [60]


async def test_retry_settings_are_not_sent_in_the_payload(http, sleeps):
    http.reply = replies(200)
    await call(retry_enabled=True, max_retries=1, quotation_no='Q1')
    assert json.loads(http.requests[0].content)['payload'] == {'quotation_no': 'Q1'}


async def test_max_retries_is_capped(http, sleeps):
    http.reply = replies(*([503] * 11))
    await call(retry_enabled=True, max_retries=50, retry_window_seconds=1)
    assert len(http.requests) == 11


async def test_bad_retry_settings_fall_back_to_defaults(http, sleeps):
    http.reply = replies(503, 200)
    out = await call(retry_enabled=True, max_retries='abc', retry_window_seconds=None)
    assert json.loads(out) == OK_BODY
    assert len(http.requests) == 2
    assert sleeps == [retry_delays(5, 900)[0]]
