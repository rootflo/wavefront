import time
from datetime import datetime
from typing import Dict, Any, Optional
from collections import defaultdict

from ..types import AuthenticatorABC, AuthResult, TokenResult, HealthStatus, UserInfo
from .config import EmailPasswordConfig


class EmailPasswordAuthenticator(AuthenticatorABC):
    """Email and password authenticator implementation."""

    def __init__(self, config: EmailPasswordConfig):
        self.config = config
        self.failed_attempts = defaultdict(list)  # Track failed login attempts

    @staticmethod
    def validate_config_static(config: Dict[str, Any]) -> bool:
        """Validate email/password configuration without creating an instance."""
        # Check password policy requirements
        policy = config.get('password_policy', {})
        required_fields = ['min_length', 'max_attempts', 'lockout_duration']

        for field in required_fields:
            if field not in policy:
                raise ValueError(f'password_policy.{field} is required')

        # Validate values
        if policy['min_length'] < 6:
            raise ValueError('password_policy.min_length must be at least 6')

        if policy['max_attempts'] < 1:
            raise ValueError('password_policy.max_attempts must be at least 1')

        if policy['lockout_duration'] < 60:  # At least 1 minute
            raise ValueError(
                'password_policy.lockout_duration must be at least 60 seconds'
            )

        return True

    # We are not using this method, coz db dependency needs to be injected
    def authenticate(self, credentials: Dict[str, Any]) -> AuthResult:
        """
        Authenticate user with email and password.

        Args:
            credentials: {"email": "user@example.com", "password": "secret"}

        Returns:
            AuthResult: Authentication result
        """
        email = credentials.get('email')
        password = credentials.get('password')

        if not email or not password:
            return AuthResult(
                success=False,
                error='Email and password are required',
                error_code='MISSING_CREDENTIALS',
            )

        # Check rate limiting
        if self.config.rate_limit_enabled and self._is_rate_limited(email):
            return AuthResult(
                success=False,
                error='Too many failed attempts. Please try again later.',
                error_code='RATE_LIMITED',
            )

        # This would typically validate against a database
        # For now, we'll return a placeholder implementation
        # The actual validation logic will be integrated with the existing user repository

        # Simulate password validation (this will be replaced with actual DB validation)
        if not self._validate_password_strength(password):
            return AuthResult(
                success=False,
                error='Password does not meet security requirements',
                error_code='WEAK_PASSWORD',
            )

        # This is a placeholder - actual implementation will validate against database
        # and be integrated with the existing user repository
        user_info = UserInfo(
            email=email,
            name=email.split('@')[0],  # Placeholder name
            provider='email_password',
        )

        return AuthResult(success=True, user_info=user_info)

    def validate_config(self) -> bool:
        """Validate the email/password configuration."""
        try:
            # Check password policy requirements
            policy = self.config.password_policy
            required_fields = ['min_length', 'max_attempts', 'lockout_duration']

            for field in required_fields:
                if field not in policy:
                    return False

            # Validate values
            if policy['min_length'] < 6:
                return False

            if policy['max_attempts'] < 1:
                return False

            if policy['lockout_duration'] < 60:  # At least 1 minute
                return False

            return True

        except Exception:
            return False

    def get_authorization_url(self, state: Optional[str] = None) -> Optional[str]:
        """Email/password doesn't need authorization URL."""
        return None

    def handle_callback(self, callback_data: Dict[str, Any]) -> AuthResult:
        """Email/password doesn't use OAuth callbacks."""
        return AuthResult(
            success=False,
            error="Email/password authentication doesn't support callbacks",
            error_code='NOT_SUPPORTED',
        )

    def refresh_token(self, refresh_token: str) -> TokenResult:
        """Email/password doesn't use refresh tokens directly."""
        return TokenResult(
            success=False,
            error="Email/password authentication doesn't support token refresh",
        )

    def logout(self, user_session: Dict[str, Any]) -> bool:
        """Handle user logout for email/password authentication."""
        # Clear any cached failed attempts for this user
        user_id = user_session.get('user_id')
        if user_id:
            self.failed_attempts.pop(user_id, None)
        return True

    def get_health_status(self) -> HealthStatus:
        """Get health status of email/password authenticator."""
        return HealthStatus(
            healthy=True,
            message='Email/password authenticator is operational',
            last_check=datetime.now(),
            details={
                'config_valid': self.validate_config(),
                'rate_limiting_enabled': self.config.rate_limit_enabled,
                'two_factor_enabled': self.config.two_factor_enabled,
            },
        )

    def get_user_info(self, access_token: str) -> Optional[UserInfo]:
        """Get user info - not applicable for email/password auth."""
        return None

    def _is_rate_limited(self, email: str) -> bool:
        """Check if user is rate limited based on failed attempts."""
        if not self.config.rate_limit_enabled:
            return False

        now = time.time()
        max_attempts = self.config.password_policy['max_attempts']
        lockout_duration = self.config.password_policy['lockout_duration']

        # Clean old attempts
        self.failed_attempts[email] = [
            attempt_time
            for attempt_time in self.failed_attempts[email]
            if now - attempt_time < lockout_duration
        ]

        return len(self.failed_attempts[email]) >= max_attempts

    def _record_failed_attempt(self, email: str) -> None:
        """Record a failed login attempt."""
        if self.config.rate_limit_enabled:
            self.failed_attempts[email].append(time.time())

    def _validate_password_strength(self, password: str) -> bool:
        """Validate password against configured policy."""
        policy = self.config.password_policy

        # Check minimum length
        if len(password) < policy.get('min_length', 8):
            return False

        # Check uppercase requirement
        if policy.get('require_uppercase', False) and not any(
            c.isupper() for c in password
        ):
            return False

        # Check lowercase requirement
        if policy.get('require_lowercase', False) and not any(
            c.islower() for c in password
        ):
            return False

        # Check number requirement
        if policy.get('require_numbers', False) and not any(
            c.isdigit() for c in password
        ):
            return False

        # Check special character requirement
        if policy.get('require_special_chars', False):
            special_chars = '!@#$%^&*(),.?":{}|<>'
            if not any(c in special_chars for c in password):
                return False

        return True
