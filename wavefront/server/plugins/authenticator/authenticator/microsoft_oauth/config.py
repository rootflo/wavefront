from dataclasses import dataclass, field


@dataclass
class MicrosoftOAuthConfig:
    client_id: str
    client_secret: str
    tenant_id: str
    redirect_uri: str
    client_redirect_success_url: str
    client_redirect_failure_url: str
    scopes: list[str] = field(
        default_factory=lambda: ['openid', 'email', 'profile', 'User.Read']
    )
    authority: str = 'https://login.microsoftonline.com/'
    response_type: str = 'code'
    response_mode: str = 'query'
