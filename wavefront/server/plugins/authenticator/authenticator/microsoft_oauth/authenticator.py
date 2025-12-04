import json
import requests
from datetime import datetime
from typing import Dict, Any, Optional
from urllib.parse import urlencode, urlparse

from ..types import AuthenticatorABC, AuthResult, TokenResult, HealthStatus, UserInfo
from .config import MicrosoftOAuthConfig


class MicrosoftOAuthAuthenticator(AuthenticatorABC):
    """Microsoft OAuth 2.0 authenticator implementation."""

    def __init__(self, config: MicrosoftOAuthConfig):
        self.config = config
        self.auth_url = f'{config.authority}{config.tenant_id}/oauth2/v2.0/authorize'
        self.token_url = f'{config.authority}{config.tenant_id}/oauth2/v2.0/token'
        self.graph_url = 'https://graph.microsoft.com/v1.0/me'

    @staticmethod
    def validate_config_static(config: Dict[str, Any]) -> bool:
        """Validate Microsoft OAuth configuration without creating an instance."""
        # Check required fields
        required_fields = [
            'client_id',
            'client_secret',
            'tenant_id',
            'redirect_uri',
            'client_redirect_success_url',
            'client_redirect_failure_url',
            'scopes',
        ]
        for field in required_fields:
            if not config.get(field):
                raise ValueError(f'{field} is required')

        # Validate redirect URI format
        parsed_uri = urlparse(config['redirect_uri'])
        if not parsed_uri.scheme or not parsed_uri.netloc:
            raise ValueError('redirect_uri must be a valid URL with scheme and netloc')

        # Validate client redirect URLs
        for url_field in ['client_redirect_success_url', 'client_redirect_failure_url']:
            parsed_url = urlparse(config[url_field])
            if not parsed_url.scheme or not parsed_url.netloc:
                raise ValueError(
                    f'{url_field} must be a valid URL with scheme and netloc'
                )

        # Validate scopes
        scopes = config.get('scopes', [])
        if not scopes or len(scopes) == 0:
            raise ValueError('scopes array cannot be empty')

        # Validate authority URL
        authority = config.get('authority')
        if authority and not authority.startswith('https://'):
            raise ValueError('authority must be a valid HTTPS URL')

        return True

    def authenticate(self, credentials: Dict[str, Any]) -> AuthResult:
        """
        Authenticate user with Microsoft OAuth.

        Args:
            credentials: {"authorization_code": "code", "state": "state"}

        Returns:
            AuthResult: Authentication result
        """
        authorization_code = credentials.get('authorization_code')
        # state = credentials.get('state')

        if not authorization_code:
            return AuthResult(
                success=False,
                error='Authorization code is required',
                error_code='MISSING_AUTH_CODE',
            )

        # Exchange authorization code for access token
        token_result = self._exchange_code_for_token(authorization_code)

        if not token_result.success:
            return AuthResult(
                success=False,
                error=token_result.error,
                error_code='TOKEN_EXCHANGE_FAILED',
            )

        # Get user info from Microsoft Graph
        user_info = self._get_user_info_from_graph(token_result.access_token)

        if not user_info:
            return AuthResult(
                success=False,
                error='Failed to retrieve user information from Microsoft Graph',
                error_code='USER_INFO_FAILED',
            )

        return AuthResult(
            success=True,
            user_info=user_info,
            access_token=token_result.access_token,
            refresh_token=token_result.refresh_token,
        )

    def validate_config(self) -> bool:
        """Validate the Microsoft OAuth configuration."""
        try:
            # Check required fields
            required_fields = [
                'client_id',
                'client_secret',
                'tenant_id',
                'redirect_uri',
                'client_redirect_success_url',
                'client_redirect_failure_url',
                'scopes',
            ]
            for field in required_fields:
                if not getattr(self.config, field, None):
                    return False

            # Validate redirect URI format
            parsed_uri = urlparse(self.config.redirect_uri)
            if not parsed_uri.scheme or not parsed_uri.netloc:
                return False

            # Validate client redirect URLs
            parsed_url = urlparse(self.config.client_redirect_success_url)
            if not parsed_url.scheme or not parsed_url.netloc:
                return False

            parsed_url = urlparse(self.config.client_redirect_failure_url)
            if not parsed_url.scheme or not parsed_url.netloc:
                return False

            # Validate scopes
            if not self.config.scopes or len(self.config.scopes) == 0:
                return False

            # Validate authority URL
            if not self.config.authority.startswith('https://'):
                return False

            return True

        except Exception:
            return False

    def get_authorization_url(self, state: Optional[str] = None) -> Optional[str]:
        """Get the Microsoft OAuth authorization URL."""
        if not state:
            raise ValueError("State doesn't exist Microsoft Oauth")

        state_obj = json.loads(state)

        if state_obj['auth_id'] is None:
            raise ValueError("Auth Id doesn't exist in Microsoft Oauth state")

        params = {
            'response_type': self.config.response_type,
            'client_id': self.config.client_id,
            'redirect_uri': self.config.redirect_uri,
            'scope': ' '.join(self.config.scopes),
            'state': state,
            'response_mode': self.config.response_mode,
        }

        return f'{self.auth_url}?{urlencode(params)}'

    def handle_callback(self, callback_data: Dict[str, Any]) -> AuthResult:
        """Handle Microsoft OAuth callback."""
        return self.authenticate(callback_data)

    def refresh_token(self, refresh_token: str) -> TokenResult:
        """Refresh Microsoft OAuth access token."""
        if not refresh_token:
            return TokenResult(success=False, error='Refresh token is required')

        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': self.config.client_id,
            'client_secret': self.config.client_secret,
            'scope': ' '.join(self.config.scopes),
        }

        try:
            response = requests.post(self.token_url, data=data, timeout=10)
            response.raise_for_status()

            token_data = response.json()

            return TokenResult(
                success=True,
                access_token=token_data.get('access_token'),
                refresh_token=token_data.get(
                    'refresh_token', refresh_token
                ),  # Keep old if not returned
                expires_in=token_data.get('expires_in'),
            )

        except requests.exceptions.RequestException as e:
            return TokenResult(success=False, error=f'Token refresh failed: {str(e)}')
        except json.JSONDecodeError:
            return TokenResult(
                success=False, error='Invalid response from Microsoft token endpoint'
            )

    def logout(self, user_session: Dict[str, Any]) -> bool:
        """Handle user logout for Microsoft OAuth."""
        # Microsoft doesn't have a simple token revocation endpoint like Google
        # The tokens will expire naturally, but we can log the logout
        return True

    def get_health_status(self) -> HealthStatus:
        """Get health status of Microsoft OAuth authenticator."""
        is_healthy = True
        details = {
            'config_valid': self.validate_config(),
            'tenant_id': self.config.tenant_id,
            'scopes': self.config.scopes,
        }

        # Test Microsoft Graph API connectivity
        try:
            response = requests.get('https://graph.microsoft.com', timeout=5)
            details['graph_api_reachable'] = response.status_code == 200
        except Exception:
            details['graph_api_reachable'] = False
            is_healthy = False

        return HealthStatus(
            healthy=is_healthy,
            message='Microsoft OAuth authenticator is operational'
            if is_healthy
            else 'Microsoft Graph API unreachable',
            last_check=datetime.now(),
            details=details,
        )

    def get_user_info(self, access_token: str) -> Optional[UserInfo]:
        """Get user information from Microsoft Graph using access token."""
        return self._get_user_info_from_graph(access_token)

    def _exchange_code_for_token(self, authorization_code: str) -> TokenResult:
        """Exchange authorization code for access token."""
        data = {
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'client_id': self.config.client_id,
            'client_secret': self.config.client_secret,
            'redirect_uri': self.config.redirect_uri,
            'scope': ' '.join(self.config.scopes),
        }

        try:
            response = requests.post(self.token_url, data=data, timeout=10)
            response.raise_for_status()

            token_data = response.json()

            return TokenResult(
                success=True,
                access_token=token_data.get('access_token'),
                refresh_token=token_data.get('refresh_token'),
                expires_in=token_data.get('expires_in'),
            )

        except requests.exceptions.RequestException as e:
            return TokenResult(success=False, error=f'Token exchange failed: {str(e)}')
        except json.JSONDecodeError:
            return TokenResult(
                success=False, error='Invalid response from Microsoft token endpoint'
            )

    def _get_user_info_from_graph(self, access_token: str) -> Optional[UserInfo]:
        """Get user information from Microsoft Graph API."""
        try:
            headers = {'Authorization': f'Bearer {access_token}'}
            response = requests.get(self.graph_url, headers=headers, timeout=10)
            response.raise_for_status()

            user_data = response.json()

            mail = user_data.get('mail') or user_data.get('userPrincipalName')

            return UserInfo(
                email=mail,
                first_name=(
                    user_data.get('givenName')
                    or (mail.split('@')[0] if mail and '@' in mail else None)
                ),
                last_name=user_data.get('surname'),
                user_id=user_data.get('id'),
                provider='microsoft',
                avatar_url=None,  # Microsoft Graph doesn't provide avatar URL directly
                additional_info={
                    'display_name': user_data.get('displayName'),
                    'job_title': user_data.get('jobTitle'),
                    'office_location': user_data.get('officeLocation'),
                    'preferred_language': user_data.get('preferredLanguage'),
                    'user_principal_name': user_data.get('userPrincipalName'),
                },
            )

        except Exception:
            return None
