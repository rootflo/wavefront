from typing import Any, Dict, List, Optional, Protocol, Tuple, Union
from urllib.parse import urlparse
from uuid import UUID
import json
import secrets
import time

from mailer import EmailCapability, EmailProviderType, get_email_provider_factory
from pydantic import BaseModel, field_validator

# Every connection needs at least this much to be useful, and asking for it up
# front avoids a second consent round for the common case.
DEFAULT_CAPABILITIES: List[str] = [EmailCapability.READ.value]

# Opaque OAuth `state` lives in Redis for one authorize→callback round-trip.
EMAIL_OAUTH_STATE_TTL_SECONDS = 600
_EMAIL_OAUTH_STATE_KEY_PREFIX = 'email_oauth:state:'


class _EmailOAuthStateCache(Protocol):
    def add(
        self,
        key: str,
        value: Union[str, int, float, bytes],
        expiry: int = 3600,
        nx: bool = False,
    ) -> bool: ...

    def pop_str(self, key: str, default: Any = None) -> Optional[str]: ...


class CreateOAuthAppPayload(BaseModel):
    name: str
    provider: str
    config: Dict[str, Any]
    description: Optional[str] = None


class UpdateOAuthAppPayload(BaseModel):
    name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    description: Optional[str] = None


def _require_absolute_redirect(url: Optional[str]) -> Optional[str]:
    """Post-consent redirects must be absolute http(s) URLs."""
    if url is None or url == '':
        return None
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError(
            'success_redirect_url and failure_redirect_url must be absolute '
            'http(s) URLs'
        )
    return url


class CreateEmailConnectionPayload(BaseModel):
    name: str
    provider: str
    oauth_app_id: str
    capabilities: List[str] = DEFAULT_CAPABILITIES
    success_redirect_url: Optional[str] = None
    failure_redirect_url: Optional[str] = None

    @field_validator('success_redirect_url', 'failure_redirect_url')
    @classmethod
    def _absolute_redirects(cls, value: Optional[str]) -> Optional[str]:
        return _require_absolute_redirect(value)


class AuthorizeEmailConnectionPayload(BaseModel):
    """Requested capabilities for a fresh consent or a scope upgrade."""

    capabilities: List[str] = DEFAULT_CAPABILITIES
    success_redirect_url: Optional[str] = None
    failure_redirect_url: Optional[str] = None

    @field_validator('success_redirect_url', 'failure_redirect_url')
    @classmethod
    def _absolute_redirects(cls, value: Optional[str]) -> Optional[str]:
        return _require_absolute_redirect(value)


class SendEmailPayload(BaseModel):
    to: List[str]
    subject: str
    body: str
    sender_display_name: Optional[str] = None


def parse_provider(provider: str) -> EmailProviderType:
    try:
        return EmailProviderType(provider)
    except ValueError:
        supported = ', '.join(p.value for p in EmailProviderType)
        raise ValueError(
            f'Unsupported email provider: {provider!r}. Supported: {supported}'
        ) from None


def parse_capabilities(capabilities: List[str]) -> List[EmailCapability]:
    if not capabilities:
        raise ValueError('At least one capability is required')

    parsed: List[EmailCapability] = []
    for capability in capabilities:
        try:
            value = EmailCapability(capability)
        except ValueError:
            supported = ', '.join(c.value for c in EmailCapability)
            raise ValueError(
                f'Unknown capability: {capability!r}. Supported: {supported}'
            ) from None
        if value not in parsed:
            parsed.append(value)
    return parsed


def validate_oauth_app_config(provider: str, config: Dict[str, Any]) -> None:
    """Check an OAuth app config against its provider's dataclass.

    Raises ValueError naming the offending field, which controllers surface as a
    400 rather than letting it fail later during consent.
    """
    provider_type = parse_provider(provider)
    get_email_provider_factory().validate_config(provider_type, config)


def split_client_secret(config: Dict[str, Any]) -> tuple[Dict[str, Any], str]:
    """Separate the client secret from the rest of an app config.

    The secret is stored encrypted in its own column so the remaining config can
    be handed back to admin UIs without redaction.
    """
    remaining = dict(config)
    client_secret = remaining.pop('client_secret', None)
    if not client_secret:
        raise ValueError('client_secret is required')
    return remaining, client_secret


def issue_email_oauth_state(
    cache: _EmailOAuthStateCache,
    *,
    connection_id: UUID,
    session_id: str,
    user_id: Optional[str] = None,
    success_redirect_url: Optional[str] = None,
    failure_redirect_url: Optional[str] = None,
) -> str:
    """Mint an opaque OAuth `state` nonce and persist the flow server-side.

    Providers only echo `state` back; connection id, initiating session, and
    post-consent redirects are looked up from the cache on callback — never
    trusted from the query string alone.
    """
    if not session_id:
        raise ValueError('session_id is required to start email OAuth')

    state = secrets.token_urlsafe(32)
    now = int(time.time())
    payload: Dict[str, Any] = {
        'connection_id': str(connection_id),
        'session_id': str(session_id),
        'exp': now + EMAIL_OAUTH_STATE_TTL_SECONDS,
    }
    if user_id:
        payload['user_id'] = str(user_id)
    if success_redirect_url:
        payload['s'] = success_redirect_url
    if failure_redirect_url:
        payload['f'] = failure_redirect_url

    stored = cache.add(
        f'{_EMAIL_OAUTH_STATE_KEY_PREFIX}{state}',
        json.dumps(payload, separators=(',', ':')),
        expiry=EMAIL_OAUTH_STATE_TTL_SECONDS,
        nx=True,
    )
    if not stored:
        raise ValueError('Failed to persist OAuth state')
    return state


def consume_email_oauth_state(
    cache: _EmailOAuthStateCache,
    state: str,
    *,
    session_id: Optional[str] = None,
) -> Tuple[UUID, Optional[str], Optional[str], Optional[str]]:
    """Atomically consume OAuth state. Returns connection id, redirects, user_id.

    Rejects missing, expired, already-consumed, or session-mismatched state.
    """
    if not state or not state.strip():
        raise ValueError('Invalid OAuth state')

    key = f'{_EMAIL_OAUTH_STATE_KEY_PREFIX}{state}'
    raw = cache.pop_str(key)
    if not raw:
        raise ValueError('Invalid or expired OAuth state')

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError('OAuth state payload must be a JSON object')
        connection_id = UUID(payload['connection_id'])
        stored_session_id = payload.get('session_id')
        if not stored_session_id:
            raise ValueError('OAuth state missing session binding')
        if session_id is not None and str(session_id) != str(stored_session_id):
            raise ValueError('OAuth state session mismatch')
        exp = int(payload['exp'])
        if exp < int(time.time()):
            raise ValueError('OAuth state has expired')
        success = payload.get('s')
        failure = payload.get('f')
        if success is not None:
            success = _require_absolute_redirect(success)
        if failure is not None:
            failure = _require_absolute_redirect(failure)
        user_id = payload.get('user_id')
        if user_id is not None:
            user_id = str(user_id)
    except (
        KeyError,
        TypeError,
        AttributeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError('Invalid or expired OAuth state') from exc

    return connection_id, success, failure, user_id


def is_allowed_client_redirect(url: str, web_url: str) -> bool:
    """True when `url` shares scheme+host with configured `[web].url`."""
    allowed_base = (web_url or '').strip()
    if not allowed_base:
        return False
    target = urlparse(url)
    allowed = urlparse(allowed_base)
    if target.scheme not in ('http', 'https') or not target.netloc:
        return False
    if allowed.scheme not in ('http', 'https') or not allowed.netloc:
        return False
    return (
        target.scheme == allowed.scheme
        and target.netloc.lower() == allowed.netloc.lower()
    )
