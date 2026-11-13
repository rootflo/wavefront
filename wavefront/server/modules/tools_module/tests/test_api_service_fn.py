"""trigger_api_service: returns the response body as-is, success or failure; never raises;
optional retries with exponential backoff."""

import asyncio
import json
import time

import flo_lib.http as httpx
import pytest

from tools_module.floware_api import FlowareApiClient
from tools_module.utils import api_service_fn
from tools_module.utils.api_service_fn import execute_api_service_fn, retry_delays


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
def clock(monkeypatch):
    """A fake clock: backoff waits advance it instead of sleeping, and record themselves."""

    class Clock:
        t = 0.0
        waits: list[float] = []

    async def fake_sleep(seconds):
        Clock.waits = [*Clock.waits, seconds]
        Clock.t += seconds

    Clock.t, Clock.waits = 0.0, []
    monkeypatch.setattr(api_service_fn.asyncio, 'sleep', fake_sleep)
    monkeypatch.setattr(api_service_fn, '_now', lambda: Clock.t)
    return Clock


OK_BODY = {'meta': {'status': 'success'}, 'data': {'status': 200}}


def replies(*statuses):
    """Answer each request with the next status code."""
    queue = list(statuses)

    def reply(request):
        status = queue.pop(0)
        body = OK_BODY if status == 200 else {'meta': {}, 'data': {'status': status}}
        return httpx.Response(status, json=body)

    return reply


def timing_out(clock, timeouts):
    """Every request uses up its whole timeout, then fails; the timeouts are recorded."""

    def reply(request):
        timeout = request.extensions['timeout']['read']
        timeouts.append(timeout)
        clock.t += timeout
        raise httpx.ReadTimeout('timed out', request=request)

    return reply


def test_retry_delays_double_and_fit_the_window_with_every_timeout():
    # 900s window, 6 attempts x 60s timeout = 360s, so 540s is left to wait in
    delays = retry_delays(5, 900)
    assert [round(d, 2) for d in delays] == [17.42, 34.84, 69.68, 139.35, 278.71]
    assert round(sum(delays), 6) == 900 - 6 * 60
    assert [round(d, 2) for d in retry_delays(3, 900)] == [94.29, 188.57, 377.14]
    assert retry_delays(0, 900) == []


def test_retry_delays_are_zero_when_the_window_is_too_short():
    assert retry_delays(5, 120) == [0, 0, 0, 0, 0]


async def test_retries_off_by_default(http, clock):
    http.reply = replies(503)
    out = json.loads(await call())
    assert out['data']['status'] == 503
    assert len(http.requests) == 1
    assert clock.waits == []


async def test_retries_until_success(http, clock):
    http.reply = replies(503, 502, 200)
    # 4 attempts x 60s + 70s of waiting: waits 10, 20, 40
    out = await call(retry_enabled=True, max_retries=3, retry_window_seconds=310)
    assert json.loads(out) == OK_BODY
    assert len(http.requests) == 3
    assert clock.waits == [10, 20]


async def test_gives_up_after_max_retries_with_last_body(http, clock):
    http.reply = replies(503, 503, 503)
    out = json.loads(
        await call(retry_enabled=True, max_retries=2, retry_window_seconds=183)
    )
    assert out['data']['status'] == 503
    assert len(http.requests) == 3
    assert clock.waits == [1, 2]


async def test_client_errors_are_not_retried(http, clock):
    http.reply = replies(401)
    out = json.loads(await call(retry_enabled=True, max_retries=5))
    assert out['data']['status'] == 401
    assert len(http.requests) == 1
    assert clock.waits == []


async def test_429_and_408_are_retried(http, clock):
    http.reply = replies(429, 408, 200)
    out = await call(retry_enabled=True, max_retries=2, retry_window_seconds=183)
    assert json.loads(out) == OK_BODY
    assert len(http.requests) == 3


async def test_unreachable_is_retried(http, clock):
    queue = ['boom', 200]

    def reply(request):
        if queue.pop(0) == 'boom':
            raise httpx.ConnectError('refused', request=request)
        return httpx.Response(200, json=OK_BODY)

    http.reply = reply
    out = await call(retry_enabled=True, max_retries=1, retry_window_seconds=125)
    assert json.loads(out) == OK_BODY
    assert clock.waits == [5]


async def test_unreachable_every_time_gives_error_json(http, clock):
    def reply(request):
        raise httpx.ConnectError('refused', request=request)

    http.reply = reply
    out = json.loads(
        await call(retry_enabled=True, max_retries=2, retry_window_seconds=183)
    )
    assert list(out) == ['error']
    assert 'refused' in out['error']
    assert len(clock.waits) == 2


async def test_window_caps_the_whole_node_when_every_attempt_times_out(http, clock):
    timeouts: list[float] = []
    http.reply = timing_out(clock, timeouts)
    out = json.loads(
        await call(retry_enabled=True, max_retries=5, retry_window_seconds=900)
    )
    assert list(out) == ['error']
    assert len(timeouts) == 6
    assert clock.t <= 900


async def test_short_window_cuts_attempts_short_and_stops(http, clock):
    timeouts: list[float] = []
    http.reply = timing_out(clock, timeouts)
    await call(retry_enabled=True, max_retries=5, retry_window_seconds=100)
    # 60s, then the 40s left; then nothing fits
    assert timeouts == [60, 40]
    assert clock.t == 100


async def test_no_window_means_one_plain_attempt(http, clock):
    http.reply = replies(503, 200)
    out = json.loads(
        await call(retry_enabled=True, max_retries=5, retry_window_seconds=0)
    )
    assert out['data']['status'] == 503
    assert len(http.requests) == 1


async def test_yaml_style_strings_are_accepted(http, clock):
    http.reply = replies(500, 200)
    out = await call(retry_enabled='true', max_retries='1', retry_window_seconds='180')
    assert json.loads(out) == OK_BODY
    assert clock.waits == [60]


async def test_retry_settings_are_not_sent_in_the_payload(http, clock):
    http.reply = replies(200)
    await call(retry_enabled=True, max_retries=1, quotation_no='Q1')
    assert json.loads(http.requests[0].content)['payload'] == {'quotation_no': 'Q1'}


async def test_max_retries_is_capped(http, clock):
    http.reply = replies(*([503] * 11))
    await call(retry_enabled=True, max_retries=50, retry_window_seconds=10_000)
    assert len(http.requests) == 11


async def test_bad_retry_settings_fall_back_to_defaults(http, clock):
    http.reply = replies(503, 200)
    out = await call(retry_enabled=True, max_retries='abc', retry_window_seconds=None)
    assert json.loads(out) == OK_BODY
    assert len(http.requests) == 2
    assert clock.waits == [retry_delays(5, 900)[0]]


@pytest.mark.parametrize('bad', ['nan', 'inf', float('nan'), float('-inf')])
async def test_non_finite_retry_settings_fall_back_to_defaults(http, clock, bad):
    http.reply = replies(503, 200)
    out = await call(retry_enabled=True, max_retries=bad, retry_window_seconds=bad)
    assert json.loads(out) == OK_BODY
    assert clock.waits == [retry_delays(5, 900)[0]]


async def test_tiny_window_never_gets_a_longer_first_attempt(http, clock):
    timeouts: list[float] = []
    http.reply = timing_out(clock, timeouts)
    await call(retry_enabled=True, max_retries=1, retry_window_seconds=1)
    assert timeouts == [1]
    assert clock.t == 1


async def test_no_attempt_starts_after_a_wait_overruns_the_window(
    http, clock, monkeypatch
):
    async def overrunning_sleep(seconds):
        clock.waits = [*clock.waits, seconds]
        clock.t += seconds + 1000  # the wait resumes long after the deadline

    monkeypatch.setattr(api_service_fn.asyncio, 'sleep', overrunning_sleep)
    http.reply = replies(503, 200)
    out = json.loads(
        await call(retry_enabled=True, max_retries=1, retry_window_seconds=125)
    )
    assert out['data']['status'] == 503
    assert len(http.requests) == 1


async def test_a_trickling_answer_is_cut_off_at_the_window(monkeypatch):
    real_sleep = asyncio.sleep

    async def never_finishes(request):
        await real_sleep(30)
        return httpx.Response(200, json=OK_BODY)

    real_client = httpx.AsyncClient

    def make_client(*args, **kwargs):
        kwargs['transport'] = httpx.MockTransport(never_finishes)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, 'AsyncClient', make_client)
    started = time.monotonic()
    out = json.loads(
        await call(retry_enabled=True, max_retries=1, retry_window_seconds=0.3)
    )
    assert list(out) == ['error']
    assert time.monotonic() - started < 5
