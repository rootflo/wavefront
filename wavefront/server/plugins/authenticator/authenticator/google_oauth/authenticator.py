import json
import requests
from datetime import datetime
from typing import Dict, Any, Optional
from urllib.parse import urlencode, urlparse

from ..types import AuthenticatorABC, AuthResult, TokenResult, HealthStatus, UserInfo
from .config import GoogleOAuthConfig


class GoogleOAuthAuthenticator(AuthenticatorABC):
    """Google OAuth 2.0 authenticator implementation."""

    def __init__(self, config: GoogleOAuthConfig):
        self.config = config
        self.auth_url = 'https://accounts.google.com/o/oauth2/v2/auth'
        self.token_url = 'https://oauth2.googleapis.com/token'
        self.userinfo_url = 'https://www.googleapis.com/oauth2/v2/userinfo'

    @staticmethod
    def validate_config_static(config: Dict[str, Any]) -> bool:
        """Validate Google OAuth configuration without creating an instance."""
        # Check required fields
        required_fields = [
            'client_id',
            'client_secret',
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

        return True

    def authenticate(self, credentials: Dict[str, Any]) -> AuthResult:
        """
        Authenticate user with Google OAuth.

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

        # Get user info from Google
        user_info = self._get_user_info_from_google(token_result.access_token)

        if not user_info:
            return AuthResult(
                success=False,
                error='Failed to retrieve user information from Google',
                error_code='USER_INFO_FAILED',
            )

        # Check hosted domain restriction if configured
        if self.config.hosted_domain:
            user_domain = (
                user_info.email.split('@')[1] if '@' in user_info.email else None
            )
            if user_domain != self.config.hosted_domain:
                return AuthResult(
                    success=False,
                    error=f'Email domain {user_domain} is not allowed',
                    error_code='DOMAIN_NOT_ALLOWED',
                )

        return AuthResult(
            success=True,
            user_info=user_info,
            access_token=token_result.access_token,
            refresh_token=token_result.refresh_token,
        )

    def validate_config(self) -> bool:
        """Validate the Google OAuth configuration."""
        try:
            # Check required fields
            required_fields = [
                'client_id',
                'client_secret',
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

            return True

        except Exception:
            return False

    def get_authorization_url(self, state: Optional[str] = None) -> Optional[str]:
        """Get the Google OAuth authorization URL."""
        if not state:
            raise ValueError("State doesn't exist Google Oauth")

        state_obj = json.loads(state)

        if state_obj['auth_id'] is None:
            raise ValueError("Auth Id doesn't exist in Google Oauth state")

        params = {
            'response_type': 'code',
            'client_id': self.config.client_id,
            'redirect_uri': self.config.redirect_uri,
            'scope': ' '.join(self.config.scopes),
            'state': state,
            'access_type': self.config.access_type,
            'prompt': self.config.prompt,
        }

        if self.config.hosted_domain:
            params['hd'] = self.config.hosted_domain

        return f'{self.auth_url}?{urlencode(params)}'

    def handle_callback(self, callback_data: Dict[str, Any]) -> AuthResult:
        """Handle Google OAuth callback."""
        return self.authenticate(callback_data)

    def refresh_token(self, refresh_token: str) -> TokenResult:
        """Refresh Google OAuth access token."""
        if not refresh_token:
            return TokenResult(success=False, error='Refresh token is required')

        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': self.config.client_id,
            'client_secret': self.config.client_secret,
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
                success=False, error='Invalid response from Google token endpoint'
            )

    def logout(self, user_session: Dict[str, Any]) -> bool:
        """Handle user logout for Google OAuth."""
        # Optionally revoke Google tokens
        access_token = user_session.get('access_token')
        if access_token:
            try:
                revoke_url = (
                    f'https://oauth2.googleapis.com/revoke?token={access_token}'
                )
                requests.post(revoke_url, timeout=5)
            except Exception:
                pass  # Non-critical if revocation fails

        return True

    def get_health_status(self) -> HealthStatus:
        """Get health status of Google OAuth authenticator."""
        is_healthy = True
        details = {
            'config_valid': self.validate_config(),
            'hosted_domain': self.config.hosted_domain,
            'scopes': self.config.scopes,
        }

        # Test Google OAuth endpoints connectivity
        try:
            response = requests.get('https://www.googleapis.com', timeout=5)
            details['google_api_reachable'] = response.status_code == 200
        except Exception:
            details['google_api_reachable'] = False
            is_healthy = False

        return HealthStatus(
            healthy=is_healthy,
            message='Google OAuth authenticator is operational'
            if is_healthy
            else 'Google APIs unreachable',
            last_check=datetime.now(),
            details=details,
        )

    def get_user_info(self, access_token: str) -> Optional[UserInfo]:
        """Get user information from Google using access token."""
        return self._get_user_info_from_google(access_token)

    def _exchange_code_for_token(self, authorization_code: str) -> TokenResult:
        """Exchange authorization code for access token."""
        data = {
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'client_id': self.config.client_id,
            'client_secret': self.config.client_secret,
            'redirect_uri': self.config.redirect_uri,
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
                success=False, error='Invalid response from Google token endpoint'
            )

    def _get_user_info_from_google(self, access_token: str) -> Optional[UserInfo]:
        """Get user information from Google API."""
        try:
            headers = {'Authorization': f'Bearer {access_token}'}
            response = requests.get(self.userinfo_url, headers=headers, timeout=10)
            response.raise_for_status()

            user_data = response.json()

            return UserInfo(
                email=user_data.get('email'),
                first_name=user_data.get('first_name'),
                last_name=user_data.get('last_name'),
                user_id=user_data.get('id'),
                provider='google',
                avatar_url=user_data.get('picture'),
                additional_info={
                    'given_name': user_data.get('given_name'),
                    'family_name': user_data.get('family_name'),
                    'locale': user_data.get('locale'),
                    'verified_email': user_data.get('verified_email'),
                },
            )

        except Exception:
            return None
