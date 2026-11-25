"""What leaves the process: event and breadcrumb scrubbing for Sentry.

Runs after the SDK's own filtering (``send_default_pii=False`` and the
``EventScrubber`` denylist). This module covers what those miss:

- request headers: only an allowlist keeps its values, because credentials
  arrive under many names (``x-auth-token``, ``api-key``, provider signature
  headers) that an exact-match denylist cannot anticipate;
- a second event for an exception that was already reported (log, then
  re-raise);
- URLs anywhere in the text: the query string, fragment and any
  ``user:password@`` part are cut, for every scheme (``https``, ``wss``,
  ``s3``, ``postgresql``, ...);
- email addresses in messages, exception text, log ``extra`` and breadcrumb
  data;
- outbound HTTP breadcrumbs keep only the scheme and host, since paths can
  hold secrets too (webhook URLs).

Both hooks fail closed: if scrubbing raises, the event or breadcrumb is
dropped rather than sent unscrubbed.

Nothing here imports ``sentry_sdk``; the hooks are plain functions over the
event dictionaries, so they can be tested without a client.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from opentelemetry import trace as otel_trace

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
_EMAIL_MASK = '[email]'
_NO_REQUEST_ID = 'NO-REQUEST-ID'
# Set on an exception object once an event for it has been sent.
_REPORTED_ATTR = '_wf_sentry_reported'
# Nested containers deeper than this are replaced rather than walked.
_MAX_DEPTH = 10

_SCHEME = r'[a-z][a-z0-9+.\-]*://'
# `scheme://user:password@host`: the credentials part.
_URL_USERINFO_RE = re.compile(rf'({_SCHEME})[^\s/?#@\'"<>]+@', re.IGNORECASE)
# Keeps scheme, host and path; drops the query string and fragment.
_URL_QUERY_RE = re.compile(rf'({_SCHEME}[^\s?#\'"<>]+)[?#][^\s\'"<>]*', re.IGNORECASE)
_EMAIL_RE = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')


def redact_text(text: str) -> str:
    """Strip URL credentials, query strings and fragments; mask emails."""
    text = _URL_USERINFO_RE.sub(rf'\1{FILTERED}@', text)
    text = _URL_QUERY_RE.sub(r'\1', text)
    return _EMAIL_RE.sub(_EMAIL_MASK, text)


def _redact_value(value: Any, depth: int = 0) -> Any:
    """``redact_text`` over every string in a nested dict or list."""
    if isinstance(value, str):
        return redact_text(value)
    if depth >= _MAX_DEPTH:
        return value if isinstance(value, (int, float, bool, type(None))) else FILTERED
    if isinstance(value, dict):
        return {key: _redact_value(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_value(item, depth + 1) for item in value]
    return value


def _strip_url(url: str) -> str:
    """A URL without query string, fragment or credentials, emails masked."""
    for separator in ('?', '#'):
        url = url.split(separator, 1)[0]
    return redact_text(url)


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


def _scrub_request(event: dict[str, Any]) -> None:
    request = event.get('request')
    if not isinstance(request, dict):
        return
    if request.get('query_string'):
        request['query_string'] = FILTERED
    url = request.get('url')
    if isinstance(url, str):
        request['url'] = _strip_url(url)
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
