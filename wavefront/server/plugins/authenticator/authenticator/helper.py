from typing import Dict, Any, Optional, Union
from datetime import datetime
import json

from .types import AuthenticatorType, UserInfo, AuthResult


def validate_email(email: str) -> bool:
    """Validate email format."""
    if not email or '@' not in email:
        return False

    parts = email.split('@')
    if len(parts) != 2:
        return False

    local, domain = parts
    if not local or not domain:
        return False

    # Basic domain validation
    if '.' not in domain:
        return False

    return True


def parse_authenticator_config(
    config_json: Union[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Parse authenticator configuration from JSON or dict."""
    if isinstance(config_json, str):
        try:
            return json.loads(config_json)
        except json.JSONDecodeError:
            return {}
    elif isinstance(config_json, dict):
        return config_json
    else:
        return {}


def create_error_response(
    message: str, error_code: str = 'UNKNOWN_ERROR'
) -> AuthResult:
    """Create a standardized error response."""
    return AuthResult(success=False, error=message, error_code=error_code)


def create_success_response(
    user_info: UserInfo,
    access_token: Optional[str] = None,
    refresh_token: Optional[str] = None,
) -> AuthResult:
    """Create a standardized success response."""
    return AuthResult(
        success=True,
        user_info=user_info,
        access_token=access_token,
        refresh_token=refresh_token,
    )


def normalize_user_info(user_data: Dict[str, Any], provider: str) -> UserInfo:
    """Normalize user information from different providers."""
    # Extract common fields
    email = (
        user_data.get('email')
        or user_data.get('mail')
        or user_data.get('userPrincipalName')
    )
    name = user_data.get('name') or user_data.get('displayName')

    # If no name, try to construct from given/family names
    if not name:
        given_name = user_data.get('given_name') or user_data.get('givenName')
        family_name = user_data.get('family_name') or user_data.get('surname')
        if given_name and family_name:
            name = f'{given_name} {family_name}'
        elif given_name:
            name = given_name
        elif family_name:
            name = family_name

    # Fallback to email prefix if no name
    if not name and email:
        name = email.split('@')[0]

    return UserInfo(
        email=email,
        name=name,
        user_id=user_data.get('id') or user_data.get('sub'),
        provider=provider,
        avatar_url=user_data.get('picture') or user_data.get('avatar_url'),
        additional_info=user_data,
    )


def get_authenticator_display_name(auth_type: AuthenticatorType) -> str:
    """Get human-readable display name for authenticator type."""
    display_names = {
        AuthenticatorType.EMAIL_PASSWORD: 'Email & Password',
        AuthenticatorType.GOOGLE_OAUTH: 'Google OAuth',
        AuthenticatorType.MICROSOFT_OAUTH: 'Microsoft OAuth',
        AuthenticatorType.SAML: 'SAML',
        AuthenticatorType.LDAP: 'LDAP',
    }
    return display_names.get(auth_type, str(auth_type))


def is_oauth_provider(auth_type: AuthenticatorType) -> bool:
    """Check if authenticator type is an OAuth provider."""
    oauth_types = {AuthenticatorType.GOOGLE_OAUTH, AuthenticatorType.MICROSOFT_OAUTH}
    return auth_type in oauth_types


def extract_domain_from_email(email: str) -> Optional[str]:
    """Extract domain from email address."""
    if not email or '@' not in email:
        return None
    return email.split('@')[1]


def format_scopes(scopes: list[str]) -> str:
    """Format scopes list for OAuth requests."""
    if not scopes:
        return ''
    return ' '.join(scopes)


def log_authentication_attempt(
    auth_type: AuthenticatorType,
    email: str,
    success: bool,
    error_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Create authentication log entry."""
    return {
        'timestamp': datetime.now().isoformat(),
        'auth_type': str(auth_type),
        'email': email,
        'success': success,
        'error_code': error_code,
    }
