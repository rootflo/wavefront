"""Tests for common_module.error_reporting (Sentry, errors only).

Events are captured in-process by a transport that appends to a list; nothing
is sent over the network. The numbered comments are stable test ids.
"""

from __future__ import annotations

import glob
import http.client
import http.server
import json
import logging
import subprocess
import sys
import threading
import tomllib
from pathlib import Path

import pytest
import sentry_sdk
from fastapi import FastAPI, Request, WebSocket
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from sentry_sdk.transport import Transport

from common_module.error_reporting import (
    ErrorReportingSettings,
    configure_error_reporting,
    error_reporting_enabled,
    shutdown_error_reporting,
)
from common_module.error_reporting import bootstrap, scrubbing
from common_module.log.logger import logger
from common_module.middleware.request_id_middleware import request_id_context

DSN = 'https://public@example.invalid/1'
SERVER_ROOT = Path(__file__).resolve().parents[3]


class CapturingTransport(Transport):
    def __init__(self) -> None:
        super().__init__()
        self.envelopes: list = []

    def capture_envelope(self, envelope) -> None:
        self.envelopes.append(envelope)

    @property
    def events(self) -> list[dict]:
        return [
            item.payload.json
            for envelope in self.envelopes
            for item in envelope.items
            if item.type == 'event'
        ]


@pytest.fixture(autouse=True)
def clean_sentry():
    bootstrap._reset_for_tests()
    previous_level = logger.level
    logger.setLevel(logging.DEBUG)
    yield
    logger.setLevel(previous_level)
    bootstrap._reset_for_tests()


def start(frameworks=(), **overrides) -> CapturingTransport:
    transport = CapturingTransport()
    settings = ErrorReportingSettings(service_name='test-service', dsn=DSN, **overrides)
    assert configure_error_reporting(
        settings, frameworks=frameworks, _transport=transport
    )
    return transport


def only_event(transport: CapturingTransport) -> dict:
    events = transport.events
    assert len(events) == 1, events
    return events[0]


_SOURCE_CONTEXT_KEYS = ('pre_context', 'context_line', 'post_context')


def runtime_data(event: dict) -> str:
    """The event as JSON, minus the source lines Sentry quotes around frames.

    Those lines are our own (public) code, and in these tests they contain the
    very literals the assertions look for. What must not leak is runtime data.
    """
    event = json.loads(json.dumps(event))
    for exception in (event.get('exception') or {}).get('values', []):
        for frame in (exception.get('stacktrace') or {}).get('frames', []):
            for key in _SOURCE_CONTEXT_KEYS:
                frame.pop(key, None)
    for thread in (event.get('threads') or {}).get('values', []):
        for frame in (thread.get('stacktrace') or {}).get('frames', []):
            for key in _SOURCE_CONTEXT_KEYS:
                frame.pop(key, None)
    return json.dumps(event)


def breadcrumb_messages(event: dict) -> list[str]:
    return [
        crumb.get('message') or ''
        for crumb in (event.get('breadcrumbs') or {}).get('values', [])
    ]


def failing_app() -> FastAPI:
    app = FastAPI()

    @app.get('/boom')
    async def boom_get():
        raise RuntimeError('boom')

    @app.post('/boom')
    async def boom_post(request: Request):
        await request.json()  # the body has been read when the error happens
        raise RuntimeError('boom')

    return app


# 1
def test_no_dsn_disables_without_calling_init(monkeypatch):
    calls = []
    monkeypatch.setattr(sentry_sdk, 'init', lambda *a, **k: calls.append(1))

    assert configure_error_reporting(ErrorReportingSettings(service_name='s')) is False
    assert calls == []
    assert error_reporting_enabled() is False


# 2
def test_init_failure_is_contained(monkeypatch):
    def broken_init(*args, **kwargs):
        raise RuntimeError('init exploded')

    monkeypatch.setattr(sentry_sdk, 'init', broken_init)
    settings = ErrorReportingSettings(service_name='s', dsn=DSN)

    assert configure_error_reporting(settings) is False
    assert error_reporting_enabled() is False


# 3
def test_second_call_does_not_reinitialise():
    first = start()
    second = CapturingTransport()
    settings = ErrorReportingSettings(service_name='other', dsn=DSN)

    assert configure_error_reporting(settings, _transport=second) is True
    assert sentry_sdk.get_client().transport is first


# 4
def test_settings_from_config(caplog):
    missing = ErrorReportingSettings.from_config({}, default_service_name='floware')
    assert missing.service_name == 'floware'
    assert missing.dsn is None
    assert missing.environment == 'dev'
    assert missing.sample_rate == 1.0
    assert missing.breadcrumb_level == logging.WARNING

    empty = ErrorReportingSettings.from_config(
        {
            'env_config': {'app_env': 'riskcovry-dev'},
            'sentry': {
                'dsn': '  ',
                'environment': '',
                'release': '',
                'sample_rate': '',
                'breadcrumb_level': '',
            },
        },
        default_service_name='floware',
    )
    assert empty.dsn is None
    assert empty.release is None
    assert empty.environment == 'riskcovry-dev'
    assert empty.sample_rate == 1.0
    assert empty.breadcrumb_level == logging.WARNING

    full = ErrorReportingSettings.from_config(
        {
            'env_config': {'app_env': 'ignored'},
            'sentry': {
                'service_name': 'floware-api',
                'dsn': DSN,
                'environment': 'qa',
                'release': 'abc123',
                'sample_rate': '0.25',
                'breadcrumb_level': 'info',
            },
        },
        default_service_name='floware',
    )
    assert full == ErrorReportingSettings(
        service_name='floware-api',
        dsn=DSN,
        environment='qa',
        release='abc123',
        sample_rate=0.25,
        breadcrumb_level=logging.INFO,
    )

    with caplog.at_level(logging.WARNING):
        for bad in ('abc', '1.5', '-0.1', 'nan'):
            settings = ErrorReportingSettings.from_config(
                {'sentry': {'sample_rate': bad}}, default_service_name='s'
            )
            assert settings.sample_rate == 1.0
        loud = ErrorReportingSettings.from_config(
            {'sentry': {'breadcrumb_level': 'loud'}}, default_service_name='s'
        )
    assert loud.breadcrumb_level == logging.WARNING
    assert 'sample_rate' in caplog.text
    assert 'breadcrumb_level' in caplog.text


# 5
def test_only_planned_integrations_are_enabled():
    start(frameworks=('fastapi',))
    enabled = set(sentry_sdk.get_client().integrations)

    for absent in ('openai', 'anthropic', 'httpx', 'sqlalchemy', 'redis', 'argv'):
        assert absent not in enabled
    for present in ('logging', 'otlp', 'fastapi', 'starlette'):
        assert present in enabled


# 6
def test_unknown_framework_is_skipped(caplog):
    with caplog.at_level(logging.WARNING):
        start(frameworks=('django',))
    assert 'django' in caplog.text
    assert error_reporting_enabled() is True


# 7
def test_error_log_inside_except_sends_one_event_with_exception():
    transport = start()
    try:
        raise ValueError('bad input')
    except ValueError:
        logger.error('processing failed')

    event = only_event(transport)
    assert event['exception']['values'][-1]['type'] == 'ValueError'
    assert event['tags']['service'] == 'test-service'


# 8
def test_log_then_reraise_reports_once():
    transport = start()
    try:
        try:
            raise ValueError('bad input')
        except ValueError:
            logger.error('processing failed')
            raise
    except ValueError as exc:
        # Another error in between, as under Celery: Sentry's own dedupe only
        # remembers the last exception, so only the repeat filter catches this.
        try:
            raise KeyError('unrelated')
        except KeyError:
            logger.error('unrelated failure')
        sentry_sdk.capture_exception(exc)

    types = [event['exception']['values'][-1]['type'] for event in transport.events]
    assert types == ['ValueError', 'KeyError']


# 9
def test_different_exceptions_are_both_reported():
    transport = start()
    for message in ('first', 'second'):
        try:
            raise ValueError(message)
        except ValueError:
            logger.error('processing failed')

    assert len(transport.events) == 2


# 10
def test_event_inside_otel_span_is_linked():
    transport = start()
    tracer = TracerProvider().get_tracer(__name__)
    with tracer.start_as_current_span('work') as span:
        trace_id = trace.format_trace_id(span.get_span_context().trace_id)
        try:
            raise ValueError('bad input')
        except ValueError:
            logger.error('processing failed')

    event = only_event(transport)
    assert event['contexts']['trace']['trace_id'] == trace_id
    assert event['tags']['otel.trace_id'] == trace_id


# 11
def test_event_outside_span_has_no_otel_tag():
    transport = start()
    logger.error('no span here')

    assert 'otel.trace_id' not in only_event(transport)['tags']


# 12
_OTEL_STATE_SCRIPT = """
import json
from opentelemetry import propagate, trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from sentry_sdk.transport import Transport

# What common_module.telemetry sets up: an SDK provider with a processor, and
# the W3C trace-context propagator only.
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)
propagate.set_global_textmap(TraceContextTextMapPropagator())
before = len(provider._active_span_processor._span_processors)

from common_module.error_reporting import ErrorReportingSettings, configure_error_reporting


class Discard(Transport):
    def capture_envelope(self, envelope):
        pass


ok = configure_error_reporting(
    ErrorReportingSettings(service_name='s', dsn='https://public@example.invalid/1'),
    frameworks=('fastapi',),
    _transport=Discard(),
)
print(json.dumps({
    'ok': ok,
    'same_provider': trace.get_tracer_provider() is provider,
    'processors': [before, len(provider._active_span_processor._span_processors)],
    'propagator': type(propagate.get_global_textmap()).__name__,
}))
"""


def test_otel_global_state_is_untouched():
    # A fresh interpreter: the SDK runs each integration's one-time setup once
    # per process, so in this worker an earlier test may already have done it.
    result = subprocess.run(
        [sys.executable, '-c', _OTEL_STATE_SCRIPT],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    state = json.loads(result.stdout.strip().splitlines()[-1])

    assert state['ok'] is True
    assert state['same_provider'] is True
    assert state['processors'] == [1, 1]
    assert state['propagator'] == 'TraceContextTextMapPropagator'


# 13
def test_request_headers_keep_only_allowlisted_values():
    transport = start(frameworks=('fastapi',))
    secret_headers = {
        'x-auth-token': 'auth-token-value',
        'api-key': 'api-key-value',
        'x-webhook-secret': 'webhook-secret-value',
        'x-hub-signature-256': 'signature-value',
        'x-amz-security-token': 'amz-token-value',
        'referer': 'https://app.example/login?token=referer-secret',
        'forwarded': 'for=203.0.113.9',
        'true-client-ip': '203.0.113.9',
    }
    client = TestClient(failing_app(), raise_server_exceptions=False)
    client.get(
        '/boom',
        headers={
            **secret_headers,
            'user-agent': 'pytest-agent',
            'x-flo-request-id': 'req-77',
        },
    )

    event = only_event(transport)
    headers = event['request']['headers']
    for name in secret_headers:
        assert headers.get(name) == '[Filtered]', name
    assert headers.get('user-agent') == 'pytest-agent'
    assert headers.get('x-flo-request-id') == 'req-77'
    serialized = runtime_data(event)
    for value in (*secret_headers.values(), 'referer-secret'):
        assert value not in serialized, value


# 14
def test_secret_request_headers_are_filtered():
    transport = start(frameworks=('fastapi',))
    secret_headers = {
        'x-rootflo-key': 'key-value',
        'x-rootflo-signature': 'signature-value',
        'x-passthrough': 'passthrough-value',
        'x-forwarded-client-cert': 'cert-value',
        'authorization': 'Bearer token-value',
        'cookie': 'session=cookie-value',
    }
    client = TestClient(failing_app(), raise_server_exceptions=False)
    client.get('/boom', headers={**secret_headers, 'user-agent': 'pytest-agent'})

    headers = only_event(transport)['request']['headers']
    for name in secret_headers:
        assert headers.get(name) == '[Filtered]', name
    assert headers.get('user-agent') == 'pytest-agent'


# 15
def test_query_string_is_removed():
    transport = start(frameworks=('fastapi',))
    client = TestClient(failing_app(), raise_server_exceptions=False)
    client.get('/boom?token=query-secret&page=2')

    event = only_event(transport)
    assert event['request']['query_string'] == '[Filtered]'
    assert '?' not in event['request']['url']
    assert 'query-secret' not in runtime_data(event)


# 16
def test_emails_are_masked():
    transport = start()
    logger.warning('lookup for crumb.user@example.com')
    try:
        raise ValueError('no account for exc.user@example.com')
    except ValueError:
        logger.error('login failed for log.user@example.com')

    event = only_event(transport)
    serialized = runtime_data(event)
    for address in (
        'crumb.user@example.com',
        'exc.user@example.com',
        'log.user@example.com',
    ):
        assert address not in serialized
    assert '[email]' in event['logentry']['message']
    assert '[email]' in event['exception']['values'][-1]['value']
    assert any('[email]' in message for message in breadcrumb_messages(event))


# 17
def test_local_variables_are_not_sent():
    transport = start()

    def handle(prompt):
        api_token = 'local-secret'  # noqa: F841 - must not reach the event
        raise ValueError('failed')

    try:
        handle('a private prompt')
    except ValueError:
        logger.error('handler failed')

    event = only_event(transport)
    frames = event['exception']['values'][-1]['stacktrace']['frames']
    assert frames
    assert all('vars' not in frame for frame in frames)
    assert 'local-secret' not in runtime_data(event)


# 18
def test_request_body_is_not_sent():
    transport = start(frameworks=('fastapi',))
    client = TestClient(failing_app(), raise_server_exceptions=False)
    client.post('/boom', json={'prompt': 'a private prompt', 'password': 'pw'})

    event = only_event(transport)
    # The SDK keeps the key, empty, and notes in _meta that config removed it.
    assert not event['request'].get('data')
    assert 'a private prompt' not in runtime_data(event)


# 19
def test_scrubbing_failure_drops_the_event(monkeypatch, caplog):
    transport = start()

    def broken(text):
        raise RuntimeError('masker broke')

    monkeypatch.setattr(scrubbing, 'redact_text', broken)
    with caplog.at_level(logging.WARNING):
        logger.error('this must not be sent')

    assert transport.events == []
    assert 'Sentry event dropped' in caplog.text


# 20
def test_request_id_tag():
    transport = start()
    token = request_id_context.set('req-123')
    try:
        logger.error('with a request')
    finally:
        request_id_context.reset(token)
    logger.error('without a request')

    with_request, without_request = transport.events
    assert with_request['tags']['request_id'] == 'req-123'
    assert 'request_id' not in without_request['tags']


# 21
def test_workspace_packages_match_the_workspace():
    root = tomllib.loads((SERVER_ROOT / 'pyproject.toml').read_text())
    on_disk = set()
    for pattern in root['tool']['uv']['workspace']['members']:
        for member in glob.glob(str(SERVER_ROOT / pattern / 'pyproject.toml')):
            project = tomllib.loads(Path(member).read_text())
            wheel = (
                project.get('tool', {})
                .get('hatch', {})
                .get('build', {})
                .get('targets', {})
                .get('wheel', {})
            )
            on_disk.update(Path(p).name for p in wheel.get('packages', []))

    assert on_disk
    assert set(bootstrap.WORKSPACE_PACKAGES) == on_disk


# 22
def test_shutdown_is_safe():
    shutdown_error_reporting()  # never configured
    transport = start()
    logger.error('pending event')
    shutdown_error_reporting(timeout=0.5)
    assert len(transport.events) == 1


# 23
class _RecordingHandler(http.server.BaseHTTPRequestHandler):
    received_headers: list = []

    def do_GET(self):
        type(self).received_headers.append(dict(self.headers))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


def test_outbound_http_breadcrumb_has_no_query():
    transport = start()
    _RecordingHandler.received_headers = []
    server = http.server.HTTPServer(('127.0.0.1', 0), _RecordingHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
        connection.request('GET', '/p?key=crumb-secret#frag')
        connection.getresponse().read()
        connection.close()
    finally:
        thread.join(timeout=5)
        server.server_close()
    logger.error('after the call')

    event = only_event(transport)
    crumbs = [
        crumb
        for crumb in event['breadcrumbs']['values']
        if crumb.get('category') == 'httplib'
    ]
    assert crumbs, 'expected an httplib breadcrumb'
    data = crumbs[-1]['data']
    assert 'http.query' not in data
    assert 'http.fragment' not in data
    # Host only: paths can hold secrets too (webhook URLs).
    assert data['url'] == f'http://127.0.0.1:{server.server_port}'
    assert 'crumb-secret' not in runtime_data(event)


# 29
def test_no_trace_headers_when_otel_linking_is_unavailable(monkeypatch):
    # With OTel linking registered, the SDK leaves propagation to OTel. Without
    # it (the OTLP import failed), trace_propagation_targets=[] is the guard.
    monkeypatch.setattr(bootstrap, '_otlp_integration', lambda: None)
    monkeypatch.setattr(sentry_sdk.scope, '_external_propagation_context_fn', None)
    start()
    _RecordingHandler.received_headers = []
    server = http.server.HTTPServer(('127.0.0.1', 0), _RecordingHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port)
        connection.request('GET', '/p')
        connection.getresponse().read()
        connection.close()
    finally:
        thread.join(timeout=5)
        server.server_close()

    assert _RecordingHandler.received_headers
    lowered = {name.lower() for name in _RecordingHandler.received_headers[0]}
    assert 'sentry-trace' not in lowered
    assert 'baggage' not in lowered


# 24
def test_subprocess_breadcrumb_is_dropped():
    crumb = {'category': 'subprocess', 'message': 'tool --password hunter2'}
    assert scrubbing.before_breadcrumb(crumb, None) is None


# 25
def test_info_logs_are_not_breadcrumbs_by_default():
    transport = start()
    logger.info('info line')
    logger.warning('warning line')
    logger.error('boom')

    messages = breadcrumb_messages(only_event(transport))
    assert 'warning line' in messages
    assert 'info line' not in messages


# 26
def test_info_breadcrumbs_when_configured():
    transport = start(breadcrumb_level=logging.INFO)
    logger.info('info line')
    logger.error('boom')

    assert 'info line' in breadcrumb_messages(only_event(transport))


# 27
def test_breadcrumb_scrubbing_failure_drops_the_breadcrumb(monkeypatch):
    def broken(text):
        raise RuntimeError('masker broke')

    monkeypatch.setattr(scrubbing, 'redact_text', broken)
    assert scrubbing.before_breadcrumb({'message': 'hello'}, None) is None


# 28
def test_urls_in_messages_lose_their_query():
    transport = start()
    url = 'https://h.example/p?key=url-secret#f'
    try:
        raise RuntimeError(f'call to {url} failed')
    except RuntimeError:
        logger.error(f'upstream error from {url}')

    serialized = runtime_data(only_event(transport))
    assert 'https://h.example/p' in serialized
    assert 'url-secret' not in serialized


# 30
def test_websocket_headers_are_filtered():
    transport = start(frameworks=('fastapi',))
    app = FastAPI()

    @app.websocket('/ws')
    async def ws(websocket: WebSocket):
        await websocket.accept()
        raise RuntimeError('socket failed')

    client = TestClient(app, raise_server_exceptions=False)
    with pytest.raises(Exception):
        with client.websocket_connect(
            '/ws', headers={'x-session-credential': 'ws-token-value'}
        ) as websocket:
            websocket.receive_text()

    # A header on no denylist: only the allowlist keeps its value out.
    event = only_event(transport)
    assert event['request']['headers']['x-session-credential'] == '[Filtered]'
    assert 'ws-token-value' not in runtime_data(event)


# 31
def test_log_params_and_extra_are_redacted():
    transport = start()
    logger.warning('crumb with extra', extra={'note': 'mail crumb.extra@example.com'})
    logger.error(
        'lookup failed for %s',
        {'email': 'param.user@example.com'},
        extra={
            'contact': 'extra.user@example.com',
            'password': 'extra-pw',
            # On EXTRA_DENYLIST only, not the SDK's default list.
            'access_token': 'extra-access-token',
            'x_rootflo_key': 'extra-rootflo-key',
        },
    )

    event = only_event(transport)
    serialized = runtime_data(event)
    for leaked in (
        'param.user@example.com',
        'extra.user@example.com',
        'crumb.extra@example.com',
        'extra-pw',
        'extra-access-token',
        'extra-rootflo-key',
    ):
        assert leaked not in serialized, leaked
    assert event['logentry']['params'] == []


# 32
def test_concurrent_configure_initialises_once(monkeypatch):
    real_init = sentry_sdk.init
    calls = []

    def counting_init(*args, **kwargs):
        calls.append(1)
        return real_init(*args, **kwargs)

    monkeypatch.setattr(sentry_sdk, 'init', counting_init)
    settings = ErrorReportingSettings(service_name='s', dsn=DSN)
    results = []
    threads = [
        threading.Thread(
            target=lambda: results.append(
                configure_error_reporting(settings, _transport=CapturingTransport())
            )
        )
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls == [1]
    assert results == [True] * 8


# 33
def test_any_scrubbing_failure_drops_the_event(monkeypatch):
    transport = start()

    def broken(event):
        raise KeyError('tags broke')

    monkeypatch.setattr(scrubbing, '_add_tags', broken)
    logger.error('this must not be sent')

    assert transport.events == []


# 34
@pytest.mark.parametrize(
    'url, secret',
    [
        ('wss://api.voice.example/v1/listen?token=ws-secret', 'ws-secret'),
        ('s3://bucket/key?X-Amz-Signature=s3-secret', 's3-secret'),
        ('HTTPS://H.EXAMPLE/p?key=upper-secret', 'upper-secret'),
        ('postgresql://app:db-password@db.internal:5432/app', 'db-password'),
        ('https://user:basic-secret@h.example/p', 'basic-secret'),
        # An IP host: the email mask cannot catch this one by accident.
        ('postgresql://app:pa$$!secret@10.0.0.5:5432/app', 'secret'),
    ],
)
def test_redact_text_handles_any_url_scheme(url, secret):
    redacted = scrubbing.redact_text(f'failed to reach {url} now')
    assert secret not in redacted
    assert redacted.startswith('failed to reach ')
    assert redacted.endswith(' now')


# 35
def test_uvicorn_access_logs_are_not_breadcrumbs():
    transport = start(breadcrumb_level=logging.INFO)
    access = logging.getLogger('uvicorn.access')
    previous = access.level
    access.setLevel(logging.INFO)
    try:
        access.info('GET /login?token=access-secret HTTP/1.1 200')
    finally:
        access.setLevel(previous)
    logger.error('boom')

    assert 'access-secret' not in runtime_data(only_event(transport))


# 36
def test_no_session_envelopes():
    transport = start(frameworks=('fastapi',))
    app = FastAPI()

    @app.get('/ok')
    async def ok():
        return {}

    client = TestClient(app)
    for _ in range(3):
        assert client.get('/ok').status_code == 200
    sentry_sdk.get_client().flush(timeout=2)

    item_types = {
        item.type for envelope in transport.envelopes for item in envelope.items
    }
    assert 'session' not in item_types
    assert 'sessions' not in item_types


# 37
def test_bad_settings_argument_does_not_raise():
    assert configure_error_reporting(None) is False  # type: ignore[arg-type]
    assert error_reporting_enabled() is False
