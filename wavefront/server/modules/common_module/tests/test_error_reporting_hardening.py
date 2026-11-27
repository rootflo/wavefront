"""Hardening from the production review: linear-time redaction, wider
redaction, request URLs, the event cap, and noisy third-party loggers."""

from __future__ import annotations

import json
import logging
import time

import pytest
import sentry_sdk
from fastapi import FastAPI
from fastapi.testclient import TestClient

from common_module.error_reporting import ErrorReportingSettings, scrubbing, throttle
from common_module.error_reporting.scrubbing import (
    MAX_TEXT_LENGTH,
    before_breadcrumb,
    before_send,
    redact_text,
)
from common_module.error_reporting.throttle import (
    PER_SOURCE_PER_MINUTE,
    EventThrottle,
)
from common_module.log.logger import logger


def _source_free(event: dict) -> str:
    """The event as JSON without the source lines Sentry quotes around frames."""
    event = json.loads(json.dumps(event))
    for container in ('exception', 'threads'):
        for value in (event.get(container) or {}).get('values', []):
            for frame in (value.get('stacktrace') or {}).get('frames', []):
                for key in ('pre_context', 'context_line', 'post_context'):
                    frame.pop(key, None)
    return json.dumps(event)


# -- redaction runs in linear time (it runs on the event loop) ------------------

ADVERSARIAL = {
    'letters': 'a' * 100_000,
    'path': '/floware/v1/' + 'a' * 100_000,
    'dotted': 'a.' * 50_000,
    'digits': '9' * 100_000,
    'almost-emails': ('a' * 60 + '@') * 1_600,
    'scheme-like': 'ab+' * 33_000,
    'input-value': 'input_value=' + 'x' * 100_000,
}


@pytest.mark.parametrize('text', ADVERSARIAL.values(), ids=ADVERSARIAL.keys())
def test_redaction_is_fast_on_adversarial_input(text):
    started = time.perf_counter()
    redacted = redact_text(text)
    elapsed = time.perf_counter() - started

    # Linear work on at most MAX_TEXT_LENGTH characters: milliseconds. The old
    # patterns took seconds on 16k characters.
    assert elapsed < 0.25, f'{elapsed:.3f}s'
    assert len(redacted) <= MAX_TEXT_LENGTH + len('...[truncated]')


@pytest.mark.parametrize(
    'text',
    ['/floware/v1/' + 'a' * 20_000, 'a.' * 10_000, ('a' * 60 + '@') * 330],
    ids=['letters', 'dotted', 'almost-emails'],
)
def test_patterns_are_linear_even_without_the_length_cap(text, monkeypatch):
    # The cap keeps input small; the patterns must not depend on it. Quadratic
    # patterns take seconds on 20k characters.
    monkeypatch.setattr(scrubbing, 'MAX_TEXT_LENGTH', 1_000_000)
    started = time.perf_counter()
    redact_text(text)
    assert time.perf_counter() - started < 0.25


def test_breadcrumb_with_a_huge_message_is_fast():
    crumb = {'message': 'Token missing in request for /' + 'a' * 100_000}
    started = time.perf_counter()
    before_breadcrumb(crumb, None)
    assert time.perf_counter() - started < 0.25


def test_a_huge_error_log_is_cheap_and_capped(start_sentry):
    transport = start_sentry()
    started = time.perf_counter()
    logger.error('Token missing in request for /' + 'a' * 100_000)
    elapsed = time.perf_counter() - started

    (event,) = transport.events
    assert elapsed < 0.5, f'{elapsed:.3f}s'
    assert len(event['logentry']['message']) <= 4096 + 3  # max_value_length


# -- what free-text redaction removes and keeps --------------------------------

REMOVED = [
    (
        'Error calling https://user:pw@api.example.com/v1/bot123:SECRET/send?key=abc',
        'SECRET',
    ),
    (
        'Error calling https://user:pw@api.example.com/v1/bot123:SECRET/send?key=abc',
        'pw@',
    ),
    ('wss://api.voice.example/v1/listen?token=ws-secret', 'ws-secret'),
    ('postgresql://app:pa/ss@db.internal:5432/app', 'pa/ss'),
    ('postgresql://app:pa$$!secret@10.0.0.5:5432/app', 'secret'),
    (
        'dup key\n[SQL: INSERT INTO users (email) VALUES (%(email)s)]\n'
        "[parameters: {'name': 'Bob Smith', 'plan': 'gold'}]",
        'Bob Smith',
    ),
    (
        "Input should be a valid string [type=string_type, input_value={'ssn': '123-45'}, input_type=dict]",
        '123-45',
    ),
    ('auth header was Bearer abcdefghijklmnopqrstuvwxyz0123', 'abcdefghijklmnop'),
    ('token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.sig-part_123 expired', 'eyJzdWIi'),
    ('key sk-proj-abcdefghijklmnopqrstuv', 'abcdefghijklmnopqrstuv'),
    ('key AKIAABCDEFGHIJKLMNOP', 'AKIAABCDEFGHIJKLMNOP'),
    ('key AIzaSyA-1234567890abcdefghijklmnopqrstu', 'AIzaSyA'),
    ('key ghp_abcdefghijklmnopqrstuvwxyz0123456789', 'ghp_abcdef'),
    ('config {"api_key": "k-123456"}', 'k-123456'),
    ('config password=hunter2xyz', 'hunter2xyz'),
    ('config client_secret: cs-value', 'cs-value'),
    ('contact bob%40example.com', 'bob%40example'),
    ('contact alice@example.co.in', 'alice@'),
    ('call +91 98765 43210', '98765 43210'),
    ('call 9876543210', '9876543210'),
    ('call +14155552671', '4155552671'),
]


@pytest.mark.parametrize('text, secret', REMOVED)
def test_redaction_removes(text, secret):
    assert secret not in redact_text(text)


KEPT = [
    'epoch 1732601234 and order 12345 took 250 ms',
    'uuid 6f1c2a9e-3b7d-4c55-9a10-2f4e8d7b1c33',
    'Token missing in request for /floware/v1/agents/42',
    'Redis get_str failed after retries: RetryError',
]


@pytest.mark.parametrize('text', KEPT)
def test_redaction_keeps_ordinary_text(text):
    assert redact_text(text) == text


def test_urls_keep_scheme_host_and_port():
    assert (
        redact_text('see http://127.0.0.1:8080/p?x=1 now')
        == 'see http://127.0.0.1:8080 now'
    )


def test_secret_looking_keys_are_filtered_at_any_depth(start_sentry):
    transport = start_sentry()
    logger.error(
        'with extra',
        extra={
            'details': {
                'id_token': 'tok-value',
                'custom_secret': 'secret-value',
                'session_id': 'session-value',
                'tags': {'ok'},
                'count': 3,
            }
        },
    )

    (event,) = transport.events
    details = event['extra']['details']
    serialized = _source_free(event)
    for value in ('tok-value', 'secret-value', 'session-value'):
        assert value not in serialized
    assert details['count'] == 3


def test_breadcrumb_data_bytes_and_secret_keys():
    # Breadcrumb data reaches the hook before the SDK serialises it.
    crumb = {'data': {'raw': b'binary-value', 'api_key': 'k', 'url': 'https://h/p?x=1'}}
    scrubbed = before_breadcrumb(crumb, None)
    assert scrubbed is not None
    assert scrubbed['data'] == {
        'raw': '[bytes]',
        'api_key': '[Filtered]',
        'url': 'https://h',
    }


# -- request URLs: scheme, host and route template only -------------------------


def _client() -> TestClient:
    app = FastAPI()

    @app.get('/v1/by-inbound-number/{phone_number}')
    async def by_number(phone_number: str):
        raise RuntimeError('lookup failed')

    return TestClient(app, raise_server_exceptions=False)


def test_matched_route_url_uses_the_template(start_sentry):
    transport = start_sentry(frameworks=('fastapi',))
    _client().get('/v1/by-inbound-number/+919876543210')

    (event,) = transport.events
    assert (
        event['request']['url']
        == 'http://testserver/v1/by-inbound-number/{phone_number}'
    )
    assert '9876543210' not in _source_free(event)


def test_unmatched_route_url_is_host_only():
    # A request no route matched is named after its raw path.
    event = {
        'transaction': '/no/such/path/alice@example.com',
        'transaction_info': {'source': 'url'},
        'request': {'url': 'http://testserver/no/such/path/alice@example.com'},
    }
    scrubbed = before_send(event, {})

    assert scrubbed is not None
    assert scrubbed['transaction'] == 'unmatched route'
    assert scrubbed['request']['url'] == 'http://testserver'


# -- start-up options -----------------------------------------------------------


def test_installed_package_scan_is_off(start_sentry):
    start_sentry()
    assert 'modules' not in sentry_sdk.get_client().integrations


def test_first_event_is_not_slow(start_sentry):
    start_sentry()
    started = time.perf_counter()
    logger.error('first event')
    assert time.perf_counter() - started < 0.15


def test_otel_exporter_failures_are_not_events(start_sentry):
    transport = start_sentry()
    logging.getLogger('opentelemetry.exporter.otlp.proto.http.trace_exporter').error(
        'Failed to export batch'
    )
    logging.getLogger('opentelemetry.sdk.trace').error('span processor failed')
    assert transport.events == []


def test_long_values_are_capped_at_4096(start_sentry):
    transport = start_sentry()
    try:
        raise ValueError('x' * 10_000)
    except ValueError:
        logger.error('capped')

    (event,) = transport.events
    assert len(event['exception']['values'][-1]['value']) <= 4096 + 3


# -- the event cap --------------------------------------------------------------


def test_one_log_call_site_is_capped_per_minute(start_sentry):
    transport = start_sentry()
    for _ in range(PER_SOURCE_PER_MINUTE + 4):
        logger.error('same call site')

    assert len(transport.events) == PER_SOURCE_PER_MINUTE


def test_different_call_sites_have_their_own_cap(start_sentry):
    transport = start_sentry()
    for _ in range(PER_SOURCE_PER_MINUTE + 2):
        logger.error('first site')
    for _ in range(PER_SOURCE_PER_MINUTE + 2):
        logger.error('second site')

    assert len(transport.events) == 2 * PER_SOURCE_PER_MINUTE


def test_process_total_is_capped(start_sentry):
    transport = start_sentry(max_events_per_minute=3)
    logger.error('one')
    logger.error('two')
    logger.error('three')
    logger.error('four')
    assert len(transport.events) == 3


def test_framework_exceptions_are_capped_too(start_sentry):
    transport = start_sentry()
    for _ in range(PER_SOURCE_PER_MINUTE + 3):
        try:
            raise ValueError('boom')
        except ValueError as exc:
            sentry_sdk.capture_exception(exc)

    assert len(transport.events) == PER_SOURCE_PER_MINUTE


def test_window_resets_and_reports_what_was_dropped():
    now = [0.0]
    cap = EventThrottle(per_minute=100, clock=lambda: now[0])
    source = ('log', 'floware', 'x.py', 1)
    results = [cap.allow(source) for _ in range(PER_SOURCE_PER_MINUTE + 3)]
    assert [allowed for allowed, _ in results] == [True] * PER_SOURCE_PER_MINUTE + [
        False
    ] * 3

    now[0] += 60
    allowed, dropped = cap.allow(source)
    assert allowed is True
    assert dropped == 3


def test_dropped_count_reaches_the_next_event(start_sentry, monkeypatch):
    transport = start_sentry()
    now = [0.0]
    monkeypatch.setattr(throttle, '_active', EventThrottle(30, clock=lambda: now[0]))

    def log_once():
        logger.error('throttled site')

    for _ in range(PER_SOURCE_PER_MINUTE + 2):
        log_once()
    now[0] += 60
    log_once()

    assert transport.events[-1]['extra']['sentry_throttled'] == 2


# -- settings -------------------------------------------------------------------


@pytest.mark.parametrize(
    'raw, expected', [('', 30), ('100', 100), ('0', 30), ('x', 30)]
)
def test_max_events_per_minute_setting(raw, expected):
    settings = ErrorReportingSettings.from_config(
        {'sentry': {'max_events_per_minute': raw}}, default_service_name='s'
    )
    assert settings.max_events_per_minute == expected


def test_breadcrumbs_below_warning_are_warned_about(caplog):
    with caplog.at_level(logging.WARNING):
        ErrorReportingSettings.from_config(
            {'sentry': {'breadcrumb_level': 'INFO'}}, default_service_name='s'
        )
    assert 'personal data' in caplog.text
