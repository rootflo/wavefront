from dataclasses import dataclass, field
from typing import Optional


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

    @staticmethod
    def required_fields() -> list[str]:
        return ['client_id', 'client_secret', 'redirect_uri']

    @property
    def authority(self) -> str:
        host = self.authority_host or 'https://login.microsoftonline.com'
        return f'{host.rstrip("/")}/{self.tenant_id}'
