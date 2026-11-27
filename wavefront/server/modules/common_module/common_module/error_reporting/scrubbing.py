"""What leaves the process: event and breadcrumb scrubbing for Sentry.

Runs after the SDK's own filtering (``send_default_pii=False`` and the
``EventScrubber`` denylist). This module covers what those miss:

- request headers: only an allowlist keeps its values, because credentials
  arrive under many names (``x-auth-token``, ``api-key``, provider signature
  headers) that an exact-match denylist cannot anticipate;
- request URLs: reduced to scheme, host and the matched route template, so
  path values (phone numbers, ids, tokens) are not sent;
- a second event for an exception that was already reported (log, then
  re-raise);
- free text (messages, exception values, breadcrumbs, log ``extra``), via
  ``redact_text``: URLs reduced to scheme and host, SQL parameters, input
  values from validation errors, bearer tokens, JWTs, well-known API-key
  formats, ``key=value`` secrets, emails and phone numbers;
- dict values under secret-looking keys (any key containing ``token``,
  ``secret``, ``password``, ...), at any depth.

Both hooks fail closed: if scrubbing raises, the event or breadcrumb is
dropped rather than sent unscrubbed.

Every pattern is anchored and length-bounded, and text is cut to
``MAX_TEXT_LENGTH`` first, so the cost is linear in the input. This runs on
the logging thread, usually the event loop.

Nothing here imports ``sentry_sdk``; the hooks are plain functions over the
event dictionaries, so they can be tested without a client.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from opentelemetry import trace as otel_trace

from common_module.error_reporting import throttle
from common_module.log.logger import logger
from common_module.middleware.request_id_middleware import get_current_request_id

# Added to the SDK's DEFAULT_DENYLIST, which the SDK applies to dict keys in
# `extra`, breadcrumb data, request data and cookies. The scrubber matches
# lower-cased keys exactly, so hyphen and underscore forms are both listed. A
# test in user_management_module checks the secret RootfloHeaders are here.
EXTRA_DENYLIST: list[str] = [
    'x-rootflo-key',
    'x_rootflo_key',
    'x-rootflo-signature',
    'x_rootflo_signature',
    'x-passthrough',
    'x_passthrough',
    'x-forwarded-client-cert',
    'x_forwarded_client_cert',
    'x-api-key',
    'x_api_key',
    'x-auth-token',
    'x_auth_token',
    'api-key',
    'auth-token',
    'auth_token',
    'app_key',
    'access_token',
    'refresh_token',
    'client_secret',
]

# Our own key check, by substring: catches `id_token`, `custom_secret`, ...
_SECRET_KEY_PARTS = (
    'password',
    'passwd',
    'secret',
    'token',
    'api_key',
    'apikey',
    'api-key',
    'authorization',
    'cookie',
    'credential',
    'private_key',
    'session',
)

# Request headers whose values are kept. Every other header keeps its name
# (useful when debugging) but not its value.
HEADER_ALLOWLIST: frozenset[str] = frozenset(
    {
        'accept',
        'accept-encoding',
        'accept-language',
        'connection',
        'content-length',
        'content-type',
        'host',
        'user-agent',
        'x-flo-request-id',
    }
)

FILTERED = '[Filtered]'
# Text longer than this is cut before any pattern runs: events keep at most
# 4096 characters per value anyway (`max_value_length` in bootstrap).
MAX_TEXT_LENGTH = 4096
_TRUNCATED = '...[truncated]'
_NO_REQUEST_ID = 'NO-REQUEST-ID'
# Set on an exception object once an event for it has been sent.
_REPORTED_ATTR = '_wf_sentry_reported'
# Nested containers deeper than this are replaced rather than walked.
_MAX_DEPTH = 10

# (pattern, replacement), applied in order. Each starts at a word boundary or
# a literal and bounds every repetition, so none is quadratic.
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Any URL, any scheme, to `scheme://host[:port]`: drops credentials, path,
    # query and fragment. Paths carry secrets too (webhook and bot-token URLs).
    (
        re.compile(
            r'\b([a-z][a-z0-9+.\-]{0,31})://'
            r'(?:[^\s/?#@\'"<>]{0,256}@)?'
            r'([^\s/?#@\'"<>:]{1,253})'
            r'(:\d{1,5})?'
            r'[^\s\'"<>]{0,4096}',
            re.IGNORECASE,
        ),
        r'\1://\2\3',
    ),
    # SQLAlchemy errors quote the statement's parameter values.
    (re.compile(r'\[parameters: [^\n]{0,8192}'), f'[parameters: {FILTERED}]'),
    # Pydantic validation errors quote the rejected input.
    (
        re.compile(r'input_value=[^\n]{0,8192}?(?=, input_type=|$)', re.MULTILINE),
        f'input_value={FILTERED}',
    ),
    (
        re.compile(
            r'\b(bearer|basic)\s{1,4}[A-Za-z0-9\-._~+/]{8,4096}=*', re.IGNORECASE
        ),
        rf'\1 {FILTERED}',
    ),
    # JWTs (also covers our own access tokens).
    (
        re.compile(
            r'\beyJ[A-Za-z0-9_\-]{4,4096}\.[A-Za-z0-9_\-]{4,4096}\.[A-Za-z0-9_\-]{0,4096}'
        ),
        FILTERED,
    ),
    # Well-known API-key formats: OpenAI/Anthropic-style, AWS, Google, GitHub, Slack.
    (
        re.compile(
            r'\b(?:'
            r'sk-[A-Za-z0-9_\-]{16,512}'
            r'|AKIA[0-9A-Z]{16}'
            r'|AIza[0-9A-Za-z_\-]{35}'
            r'|gh[pousr]_[A-Za-z0-9]{36,255}'
            r'|xox[abposr]-[A-Za-z0-9\-]{10,255}'
            r')'
        ),
        FILTERED,
    ),
    # `password=...`, `"api_key": "..."`, `token: ...` and similar.
    (
        re.compile(
            r'\b(password|passwd|pwd|secret|client_secret|token|access_token'
            r'|refresh_token|id_token|api[_\-]?key|access[_\-]?key|private[_\-]?key'
            r'|authorization)'
            r'(["\']?\s{0,3}[:=]\s{0,3}["\']?)'
            r'[^\s"\',;&}]{1,1024}',
            re.IGNORECASE,
        ),
        rf'\1\2{FILTERED}',
    ),
    # Emails, also URL-encoded (`%40`).
    (
        re.compile(
            r'[A-Za-z0-9._%+\-]{1,64}(?:@|%40)[A-Za-z0-9.\-]{1,253}\.[A-Za-z]{2,24}'
        ),
        '[email]',
    ),
    # Phone numbers: international with `+`, and 10-digit Indian mobiles.
    (re.compile(r'(?<![\w+])\+\d{1,3}(?:[ \-]?\d){6,14}\b'), '[phone]'),
    (re.compile(r'(?<![\w.\-])[6-9]\d{9}(?![\w.\-])'), '[phone]'),
)


def redact_text(text: str) -> str:
    """Remove credentials, personal data and customer values from free text."""
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH] + _TRUNCATED
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SECRET_KEY_PARTS)


def _redact_value(value: Any, depth: int = 0) -> Any:
    """``redact_text`` over every string in a nested container, keys included;
    values under secret-looking keys are replaced."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, (bytes, bytearray)):
        return '[bytes]'
    if depth >= _MAX_DEPTH:
        return value if isinstance(value, (int, float, bool, type(None))) else FILTERED
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            name = redact_text(key) if isinstance(key, str) else key
            if isinstance(key, str) and _is_secret_key(key):
                redacted[name] = FILTERED
            else:
                redacted[name] = _redact_value(item, depth + 1)
        return redacted
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_redact_value(item, depth + 1) for item in value]
    return value


def _host_only(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ''
    if parts.port:
        host = f'{host}:{parts.port}'
    return f'{parts.scheme}://{host}' if parts.scheme else FILTERED


def _sanitize_crumb_data(data: Any) -> Any:
    """Outbound HTTP breadcrumbs keep the full URL, query string included."""
    if not isinstance(data, dict):
        return data
    data.pop('http.query', None)
    data.pop('http.fragment', None)
    url = data.get('url')
    if isinstance(url, str):
        data['url'] = _host_only(url)
    return _redact_value(data)


def _exception_from_hint(hint: dict[str, Any] | None) -> BaseException | None:
    if not hint:
        return None
    exc_info = hint.get('exc_info')
    if exc_info and len(exc_info) > 1 and isinstance(exc_info[1], BaseException):
        return exc_info[1]
    record = hint.get('log_record')
    record_exc_info = getattr(record, 'exc_info', None)
    if (
        record_exc_info
        and len(record_exc_info) > 1
        and isinstance(record_exc_info[1], BaseException)
    ):
        return record_exc_info[1]
    return None


def _already_reported(hint: dict[str, Any] | None) -> bool:
    """True for a repeat event of the same exception object; marks new ones.

    Code here often logs an exception and re-raises it, which produces one
    event from the log and another from the framework. Sentry's dedupe only
    remembers the last exception it saw, and misses this when other events
    come in between (as under Celery).
    """
    exc = _exception_from_hint(hint)
    if exc is None:
        return False
    if getattr(exc, _REPORTED_ATTR, False):
        return True
    try:
        setattr(exc, _REPORTED_ATTR, True)
    except Exception:
        pass  # Some exception types refuse attributes; report them every time.
    return False


def _redact_event_text(event: dict[str, Any]) -> None:
    message = event.get('message')
    if isinstance(message, str):
        event['message'] = redact_text(message)

    logentry = event.get('logentry')
    if isinstance(logentry, dict):
        for key in ('message', 'formatted'):
            if isinstance(logentry.get(key), str):
                logentry[key] = redact_text(logentry[key])
        # `formatted` already holds the arguments, redacted. The raw params
        # can be dicts or objects that the text redaction would miss.
        if logentry.get('params'):
            logentry['params'] = []

    exceptions = event.get('exception')
    if isinstance(exceptions, dict):
        for value in exceptions.get('values') or []:
            if isinstance(value, dict) and isinstance(value.get('value'), str):
                value['value'] = redact_text(value['value'])

    if 'extra' in event:
        event['extra'] = _redact_value(event['extra'])

    breadcrumbs = event.get('breadcrumbs')
    if isinstance(breadcrumbs, dict):
        for crumb in breadcrumbs.get('values') or []:
            if not isinstance(crumb, dict):
                continue
            if isinstance(crumb.get('message'), str):
                crumb['message'] = redact_text(crumb['message'])
            if 'data' in crumb:
                crumb['data'] = _sanitize_crumb_data(crumb['data'])


def _matched_route(event: dict[str, Any]) -> str | None:
    """The route template when the framework matched one (`/users/{id}`)."""
    transaction = event.get('transaction')
    source = (event.get('transaction_info') or {}).get('source')
    if isinstance(transaction, str) and source == 'route':
        return transaction
    return None


def _scrub_request(event: dict[str, Any]) -> None:
    route = _matched_route(event)
    if 'transaction' in event and route is None:
        # Unmatched requests are named after their raw path.
        event['transaction'] = 'unmatched route'

    request = event.get('request')
    if not isinstance(request, dict):
        return
    if request.get('query_string'):
        request['query_string'] = FILTERED
    url = request.get('url')
    if isinstance(url, str):
        request['url'] = _host_only(url) + (route or '')
    headers = request.get('headers')
    if isinstance(headers, dict):
        request['headers'] = {
            name: value
            if str(name).lower() in HEADER_ALLOWLIST and isinstance(value, str)
            else FILTERED
            for name, value in headers.items()
        }
    # Only collected with send_default_pii, which is off; dropped in case.
    request.pop('cookies', None)
    request.pop('env', None)


def _otel_trace_id() -> str | None:
    context = otel_trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return otel_trace.format_trace_id(context.trace_id)


def _add_tags(event: dict[str, Any]) -> None:
    tags = event.get('tags')
    if not isinstance(tags, dict):
        tags = {}
        event['tags'] = tags

    request_id = get_current_request_id()
    if request_id and request_id != _NO_REQUEST_ID:
        tags.setdefault('request_id', request_id)

    # Tag only an id the OTLP integration actually linked, never the random
    # trace id Sentry generates when there is no OTel span.
    otel_trace_id = _otel_trace_id()
    trace_context = (event.get('contexts') or {}).get('trace') or {}
    if otel_trace_id and trace_context.get('trace_id') == otel_trace_id:
        tags.setdefault('otel.trace_id', otel_trace_id)


def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    try:
        if _already_reported(hint):
            return None
        if not throttle.allow_event(event, hint):
            return None
        _scrub_request(event)
        _redact_event_text(event)
        _add_tags(event)
        return event
    except Exception as exc:
        # Warning, never error: an error log would itself become an event.
        # The message is left out; it could quote the event being scrubbed.
        logger.warning(f'Sentry event dropped: scrubbing failed ({type(exc).__name__})')
        return None


def before_breadcrumb(
    crumb: dict[str, Any], hint: dict[str, Any] | None
) -> dict[str, Any] | None:
    try:
        # The message is the whole command line, which can hold credentials.
        if crumb.get('category') == 'subprocess':
            return None
        if 'data' in crumb:
            crumb['data'] = _sanitize_crumb_data(crumb['data'])
        message = crumb.get('message')
        if isinstance(message, str):
            crumb['message'] = redact_text(message)
        return crumb
    except Exception:
        return None
