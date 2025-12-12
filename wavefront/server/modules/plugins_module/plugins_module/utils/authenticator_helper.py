from typing import Dict, Any, List
from pydantic import BaseModel


class AddAuthenticatorPayload(BaseModel):
    auth_name: str
    auth_type: str
    config: Dict[str, Any]


def validate_google_oauth_config(config: Dict[str, Any]) -> List[str]:
    """Validate Google OAuth configuration and return list of errors."""
    errors = []

    required_fields = ['client_id', 'client_secret', 'redirect_uri']
    for field in required_fields:
        if not config.get(field):
            errors.append(f'Missing required field: {field}')

    # Validate redirect_uri format
    redirect_uri = config.get('redirect_uri')
    if redirect_uri and not (
        redirect_uri.startswith('http://') or redirect_uri.startswith('https://')
    ):
        errors.append('redirect_uri must be a valid HTTP/HTTPS URL')

    # Validate scopes
    scopes = config.get('scopes', [])
    if not isinstance(scopes, list) or len(scopes) == 0:
        errors.append('scopes must be a non-empty list')

    return errors


def validate_microsoft_oauth_config(config: Dict[str, Any]) -> List[str]:
    """Validate Microsoft OAuth configuration and return list of errors."""
    errors = []

    required_fields = ['client_id', 'client_secret', 'tenant_id', 'redirect_uri']
    for field in required_fields:
        if not config.get(field):
            errors.append(f'Missing required field: {field}')

    # Validate redirect_uri format
    redirect_uri = config.get('redirect_uri')
    if redirect_uri and not (
        redirect_uri.startswith('http://') or redirect_uri.startswith('https://')
    ):
        errors.append('redirect_uri must be a valid HTTP/HTTPS URL')

    # Validate scopes
    scopes = config.get('scopes', [])
    if not isinstance(scopes, list) or len(scopes) == 0:
        errors.append('scopes must be a non-empty list')

    # Validate authority
    authority = config.get('authority', '')
    if authority and not authority.startswith('https://'):
        errors.append('authority must be a valid HTTPS URL')

    return errors


def validate_email_password_config(config: Dict[str, Any]) -> List[str]:
    """Validate email/password configuration and return list of errors."""
    errors = []

    password_policy = config.get('password_policy', {})

    # Validate min_length
    min_length = password_policy.get('min_length', 8)
    if not isinstance(min_length, int) or min_length < 6:
        errors.append('password_policy.min_length must be an integer >= 6')

    # Validate max_attempts
    max_attempts = password_policy.get('max_attempts', 5)
    if not isinstance(max_attempts, int) or max_attempts < 1:
        errors.append('password_policy.max_attempts must be an integer >= 1')

    # Validate lockout_duration
    lockout_duration = password_policy.get('lockout_duration', 900)
    if not isinstance(lockout_duration, int) or lockout_duration < 60:
        errors.append(
            'password_policy.lockout_duration must be an integer >= 60 (seconds)'
        )

    # Validate session_timeout
    session_timeout = config.get('session_timeout', 3600)
    if not isinstance(session_timeout, int) or session_timeout < 300:
        errors.append('session_timeout must be an integer >= 300 (seconds)')

    return errors


def get_config_template(auth_type: str) -> Dict[str, Any]:
    """Get configuration template for authenticator type."""

    templates = {
        'email_password': {
            'password_policy': {
                'min_length': 8,
                'require_uppercase': True,
                'require_lowercase': True,
                'require_numbers': True,
                'require_special_chars': False,
                'max_attempts': 5,
                'lockout_duration': 900,
            },
            'two_factor_enabled': False,
            'password_reset_enabled': True,
            'session_timeout': 3600,
            'rate_limit_enabled': True,
        },
        'google_oauth': {
            'client_id': 'YOUR_GOOGLE_CLIENT_ID',
            'client_secret': 'YOUR_GOOGLE_CLIENT_SECRET',
            'redirect_uri': 'https://your-domain.com/auth/google/callback',
            'scopes': ['openid', 'email', 'profile'],
            'hosted_domain': None,
            'access_type': 'offline',
            'prompt': 'consent',
        },
        'microsoft_oauth': {
            'client_id': 'YOUR_MICROSOFT_CLIENT_ID',
            'client_secret': 'YOUR_MICROSOFT_CLIENT_SECRET',
            'tenant_id': 'YOUR_TENANT_ID',
            'redirect_uri': 'https://your-domain.com/auth/microsoft/callback',
            'scopes': ['openid', 'email', 'profile'],
            'authority': 'https://login.microsoftonline.com/',
            'response_type': 'code',
            'response_mode': 'query',
        },
    }

    return templates.get(auth_type, {})
