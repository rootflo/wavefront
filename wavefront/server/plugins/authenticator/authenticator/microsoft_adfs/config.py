from dataclasses import dataclass, field
from typing import Optional


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
    # JWKS endpoint used to verify id_token signatures.
    jwks_path: str = '/adfs/discovery/keys'
    # If set, id_token `iss` must match exactly. Leave None to skip the
    # issuer check (e.g. Authentik where iss host can differ from authority).
    expected_issuer: Optional[str] = None
    # Allowed clock skew (seconds) when checking exp/nbf claims.
    clock_skew_seconds: int = 60
    # Set to False ONLY for local testing against IdPs with self-signed certs
    # (e.g. dockerised Authentik). Must stay True for any real ADFS.
    verify_ssl: bool = True
    # When the id_token has no `email` claim, the authenticator falls back to
    # extracting a user identifier from `upn` or `unique_name`.
    # If the extracted value is a bare ID (e.g. "EMP12345"), append this domain
    # to form "emp12345@domain.com" so it matches what is stored in the DB.
    email_fallback_domain: Optional[str] = None
    # Optional regex with a single capture group to pull the ID out of a longer
    # upn/unique_name string, e.g. r"EMP\d+" or r"(?<=_)EMP\d+(?=_)".
    # When None the full local part (before '@') or post-backslash segment is used.
    user_id_pattern: Optional[str] = None
