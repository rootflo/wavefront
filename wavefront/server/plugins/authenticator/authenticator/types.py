from enum import Enum
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar, Dict, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Meta:
    status: str
    message: str
    code: int


T = TypeVar('T')


@dataclass
class AuthenticatorResult(Generic[T]):
    meta: Meta
    result: T


@dataclass
class UserInfo:
    email: str
    first_name: str
    last_name: Optional[str] = None
    user_id: Optional[str] = None
    provider: Optional[str] = None
    avatar_url: Optional[str] = None
    additional_info: Optional[Dict[str, Any]] = None


@dataclass
class AuthResult:
    success: bool
    user_info: Optional[UserInfo] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    redirect_url: Optional[str] = None


@dataclass
class TokenResult:
    success: bool
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    error: Optional[str] = None


@dataclass
class HealthStatus:
    healthy: bool
    message: str
    last_check: datetime
    details: Optional[Dict[str, Any]] = None


# Result type aliases
BooleanResult = AuthenticatorResult[bool]
AuthenticationResult = AuthenticatorResult[AuthResult]
TokenRefreshResult = AuthenticatorResult[TokenResult]
HealthCheckResult = AuthenticatorResult[HealthStatus]


class AuthenticatorType(Enum):
    EMAIL_PASSWORD = 'email_password'
    GOOGLE_OAUTH = 'google_oauth'
    MICROSOFT_OAUTH = 'microsoft_oauth'
    SAML = 'saml'
    LDAP = 'ldap'

    def __str__(self):
        return self.value


class AuthenticatorABC(ABC):
    """Abstract base class for all authenticator implementations."""

    @abstractmethod
    def authenticate(self, credentials: Dict[str, Any]) -> AuthResult:
        """
        Authenticate user with provided credentials.

        Args:
            credentials: Dictionary containing authentication data
                - For email_password: {"email": "user@example.com", "password": "secret"}
                - For OAuth: {"authorization_code": "code", "state": "state"}

        Returns:
            AuthResult: Authentication result with user info and tokens
        """
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """
        Validate the authenticator configuration.

        Returns:
            bool: True if configuration is valid, False otherwise
        """
        pass

    @abstractmethod
    def get_authorization_url(self, state: Optional[str] = None) -> Optional[str]:
        """
        Get the authorization URL for OAuth flow.

        Args:
            state: Optional state parameter for OAuth flow

        Returns:
            Optional[str]: Authorization URL for OAuth providers, None for email/password
        """
        pass

    @abstractmethod
    def handle_callback(self, callback_data: Dict[str, Any]) -> AuthResult:
        """
        Handle OAuth callback from provider.

        Args:
            callback_data: Dictionary containing callback data (code, state, etc.)

        Returns:
            AuthResult: Authentication result
        """
        pass

    @abstractmethod
    def refresh_token(self, refresh_token: str) -> TokenResult:
        """
        Refresh access token using refresh token.

        Args:
            refresh_token: Refresh token from previous authentication

        Returns:
            TokenResult: Token refresh result
        """
        pass

    @abstractmethod
    def logout(self, user_session: Dict[str, Any]) -> bool:
        """
        Handle user logout.

        Args:
            user_session: Current user session data

        Returns:
            bool: True if logout successful, False otherwise
        """
        pass

    @abstractmethod
    def get_health_status(self) -> HealthStatus:
        """
        Get the health status of the authenticator.

        Returns:
            HealthStatus: Current health status
        """
        pass

    @abstractmethod
    def get_user_info(self, access_token: str) -> Optional[UserInfo]:
        """
        Get user information using access token.

        Args:
            access_token: Valid access token

        Returns:
            Optional[UserInfo]: User information or None if failed
        """
        pass
