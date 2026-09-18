from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from uuid import UUID
import base64
import json

from mailer import EmailCapability, EmailProviderType, get_email_provider_factory
from pydantic import BaseModel, field_validator

# Every connection needs at least this much to be useful, and asking for it up
# front avoids a second consent round for the common case.
DEFAULT_CAPABILITIES: List[str] = [EmailCapability.READ.value]


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


def encode_email_oauth_state(
    connection_id: UUID,
    success_redirect_url: Optional[str] = None,
    failure_redirect_url: Optional[str] = None,
) -> str:
    """Pack connection id + post-consent URLs into the OAuth `state` param.

    Providers only echo `state` back; they do not preserve custom callback query
    params, so redirects ride along here. Plain UUID state is kept when no
    redirects are set.
    """
    if not success_redirect_url and not failure_redirect_url:
        return str(connection_id)

    payload: Dict[str, str] = {'id': str(connection_id)}
    if success_redirect_url:
        payload['s'] = success_redirect_url
    if failure_redirect_url:
        payload['f'] = failure_redirect_url
    raw = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def decode_email_oauth_state(
    state: str,
) -> Tuple[UUID, Optional[str], Optional[str]]:
    """Inverse of `encode_email_oauth_state`."""
    try:
        return UUID(state), None, None
    except ValueError:
        pass

    padded = state + '=' * (-len(state) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded.encode('ascii')))
        if not isinstance(payload, dict):
            raise ValueError('OAuth state payload must be a JSON object')
        connection_id = UUID(payload['id'])
        success = payload.get('s')
        failure = payload.get('f')
        if success is not None:
            success = _require_absolute_redirect(success)
        if failure is not None:
            failure = _require_absolute_redirect(failure)
    except (
        KeyError,
        TypeError,
        AttributeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError(f'Invalid OAuth state: {state}') from exc

    return connection_id, success, failure


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
