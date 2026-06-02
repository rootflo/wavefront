from dataclasses import dataclass, field


@dataclass
class MicrosoftADFSConfig:
    client_id: str
    client_secret: str
    # ADFS server base, e.g. 'https://fs.customer.com'
    authority: str
    redirect_uri: str
    client_redirect_success_url: str
    client_redirect_failure_url: str
    scopes: list[str] = field(default_factory=lambda: ['openid', 'profile', 'email'])
    response_type: str = 'code'
    response_mode: str = 'query'
    # Endpoint paths under `authority`. Defaults match on-prem ADFS;
    # override to point at Authentik/Keycloak (or reverse-proxied ADFS).
    authorize_path: str = '/adfs/oauth2/authorize'
    token_path: str = '/adfs/oauth2/token'
    # Set to False ONLY for local testing against IdPs with self-signed certs
    # (e.g. dockerised Authentik). Must stay True for any real ADFS.
    verify_ssl: bool = True
