from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

_DEFAULT_AUTHORITY_HOST = 'https://login.microsoftonline.com'

# Microsoft identity platform national-cloud auth hosts (no custom authorities).
_ALLOWED_AUTHORITY_HOSTNAMES = frozenset(
    {
        'login.microsoftonline.com',
        'login.microsoftonline.us',
        'login.partner.microsoftonline.cn',
    }
)


def normalize_authority_host(authority_host: Optional[str]) -> Optional[str]:
    """Validate an optional Entra authority base URL.

    Returns None to mean "use the global default". Rejects anything that is not
    HTTPS on an approved Microsoft hostname without port, path, query, or
    fragment — so a bad value cannot redirect client_secret / token traffic.
    """
    if authority_host is None:
        return None
    raw = str(authority_host).strip()
    if not raw:
        return None

    parsed = urlparse(raw.rstrip('/'))
    if parsed.scheme != 'https':
        raise ValueError('authority_host must use https')
    if parsed.username or parsed.password:
        raise ValueError('authority_host must not include credentials')
    if parsed.port is not None:
        raise ValueError('authority_host must not include a port')
    if parsed.query or parsed.fragment:
        raise ValueError('authority_host must not include query or fragment')
    if (parsed.path or '').strip('/'):
        raise ValueError('authority_host must not include a path')

    hostname = (parsed.hostname or '').lower()
    if hostname not in _ALLOWED_AUTHORITY_HOSTNAMES:
        allowed = ', '.join(sorted(_ALLOWED_AUTHORITY_HOSTNAMES))
        raise ValueError(f'authority_host hostname must be one of: {allowed}')
    return f'https://{hostname}'


@dataclass
class OutlookAppConfig:
    """One Microsoft Entra application used for delegated mailbox access.

    `tenant_id` defaults to `common` so personal and multi-tenant accounts can
    consent; single-tenant apps must set their directory id explicitly.
    """

    client_id: str
    client_secret: str
    redirect_uri: str
    tenant_id: str = field(default='common')
    authority_host: Optional[str] = None

    def __post_init__(self) -> None:
        self.authority_host = normalize_authority_host(self.authority_host)

    @staticmethod
    def required_fields() -> list[str]:
        return ['client_id', 'client_secret', 'redirect_uri']

    @property
    def authority(self) -> str:
        host = self.authority_host or _DEFAULT_AUTHORITY_HOST
        return f'{host.rstrip("/")}/{self.tenant_id}'
