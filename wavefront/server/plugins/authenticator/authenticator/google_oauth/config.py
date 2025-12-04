from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GoogleOAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    client_redirect_success_url: str
    client_redirect_failure_url: str
    scopes: list[str] = field(default_factory=lambda: ['openid', 'email', 'profile'])
    hosted_domain: Optional[str] = None  # Restrict to specific domain
    access_type: str = 'offline'  # To get refresh token
    prompt: str = 'consent'  # To ensure refresh token is always returned
