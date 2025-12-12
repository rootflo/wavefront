import threading
from typing import Dict, Optional

from .types import AuthenticatorType, AuthenticatorABC
from .email_password import EmailPasswordAuthenticator
from .google_oauth import GoogleOAuthAuthenticator
from .microsoft_oauth import MicrosoftOAuthAuthenticator
from .email_password.config import EmailPasswordConfig
from .google_oauth.config import GoogleOAuthConfig
from .microsoft_oauth.config import MicrosoftOAuthConfig


class AuthenticatorFactory:
    """Factory class for managing authenticator instances with caching and lifecycle management."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern for factory itself."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(AuthenticatorFactory, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._google_instances: Dict[str, GoogleOAuthAuthenticator] = {}
            self._microsoft_instances: Dict[str, MicrosoftOAuthAuthenticator] = {}
            self._email_instances: Dict[str, EmailPasswordAuthenticator] = {}
            self._instances_lock = threading.Lock()
            self._initialized = True

    def get_authenticator(
        self, auth_id: str, auth_type: AuthenticatorType, config: Dict[str, any]
    ) -> AuthenticatorABC:
        """
        Get or create an authenticator instance for the given auth_id.

        Args:
            auth_id: Unique ID for the authenticator instance
            auth_type: Type of authenticator (GOOGLE_OAUTH, MICROSOFT_OAUTH, EMAIL_PASSWORD)
            config: Configuration dictionary for the authenticator

        Returns:
            AuthenticatorABC: The authenticator instance

        Raises:
            ValueError: If auth_type is not supported
            RuntimeError: If authenticator initialization fails
        """
        with self._instances_lock:
            instance_cache = self._get_cache_for_type(auth_type)

            # Check if instance already exists
            if auth_id in instance_cache:
                return instance_cache[auth_id]

            # Create new instance
            authenticator = self._create_authenticator(auth_type, config)
            instance_cache[auth_id] = authenticator

            return authenticator

    def validate_config(
        self, auth_type: AuthenticatorType, config: Dict[str, any]
    ) -> bool:
        """
        Validate configuration using appropriate static validation method.

        Args:
            auth_type: Type of authenticator
            config: Configuration dictionary to validate

        Returns:
            bool: True if configuration is valid

        Raises:
            ValueError: If configuration is invalid with specific error message
        """
        if auth_type == AuthenticatorType.EMAIL_PASSWORD:
            return EmailPasswordAuthenticator.validate_config_static(config)
        elif auth_type == AuthenticatorType.GOOGLE_OAUTH:
            return GoogleOAuthAuthenticator.validate_config_static(config)
        elif auth_type == AuthenticatorType.MICROSOFT_OAUTH:
            return MicrosoftOAuthAuthenticator.validate_config_static(config)
        else:
            raise ValueError(f'Unsupported authenticator type: {auth_type}')

    def remove_authenticator(self, auth_id: str, auth_type: AuthenticatorType) -> bool:
        """
        Remove an authenticator instance from the cache.

        Args:
            auth_id: ID of the authenticator to remove
            auth_type: Type of authenticator

        Returns:
            bool: True if instance was removed, False if not found
        """
        with self._instances_lock:
            instance_cache = self._get_cache_for_type(auth_type)

            if auth_id in instance_cache:
                del instance_cache[auth_id]
                return True

            return False

    def update_authenticator(
        self, auth_id: str, auth_type: AuthenticatorType, config: Dict[str, any]
    ) -> AuthenticatorABC:
        """
        Update an authenticator instance with new configuration.
        This validates first, then removes the old instance and creates a new one.

        Args:
            auth_id: ID of the authenticator to update
            auth_type: Type of authenticator
            config: New configuration dictionary

        Returns:
            AuthenticatorABC: The updated authenticator instance
        """

        # Validate config BEFORE acquiring lock
        self.validate_config(auth_type, config)

        with self._instances_lock:
            # Remove old instance if exists
            instance_cache = self._get_cache_for_type(auth_type)
            if auth_id in instance_cache:
                del instance_cache[auth_id]

            # Create new instance WITHOUT calling get_authenticator to avoid deadlock
            authenticator = self._create_authenticator(auth_type, config)
            instance_cache[auth_id] = authenticator
            return authenticator

    def get_cached_instance_count(
        self, auth_type: Optional[AuthenticatorType] = None
    ) -> int:
        """
        Get the number of cached instances for debugging/monitoring.

        Args:
            auth_type: Optional filter by auth_type

        Returns:
            int: Number of cached instances
        """
        with self._instances_lock:
            if auth_type:
                return len(self._get_cache_for_type(auth_type))

            return (
                len(self._google_instances)
                + len(self._microsoft_instances)
                + len(self._email_instances)
            )

    def clear_all_instances(self) -> None:
        """Clear all cached instances. Useful for testing or cleanup."""
        with self._instances_lock:
            self._google_instances.clear()
            self._microsoft_instances.clear()
            self._email_instances.clear()

    def _get_cache_for_type(
        self, auth_type: AuthenticatorType
    ) -> Dict[str, AuthenticatorABC]:
        """Get the appropriate instance cache for the given auth_type."""
        if auth_type == AuthenticatorType.GOOGLE_OAUTH:
            return self._google_instances
        elif auth_type == AuthenticatorType.MICROSOFT_OAUTH:
            return self._microsoft_instances
        elif auth_type == AuthenticatorType.EMAIL_PASSWORD:
            return self._email_instances
        else:
            raise ValueError(f'Unsupported authenticator type: {auth_type}')

    def _create_authenticator(
        self, auth_type: AuthenticatorType, config: Dict[str, any]
    ) -> AuthenticatorABC:
        """Create a new authenticator instance based on type and config."""
        if auth_type == AuthenticatorType.EMAIL_PASSWORD:
            typed_config = EmailPasswordConfig(**config)
            return EmailPasswordAuthenticator(typed_config)

        elif auth_type == AuthenticatorType.GOOGLE_OAUTH:
            typed_config = GoogleOAuthConfig(**config)
            return GoogleOAuthAuthenticator(typed_config)

        elif auth_type == AuthenticatorType.MICROSOFT_OAUTH:
            typed_config = MicrosoftOAuthConfig(**config)
            return MicrosoftOAuthAuthenticator(typed_config)

        else:
            raise ValueError(f'Unsupported authenticator type: {auth_type}')


# Global factory instance
_factory_instance = None
_factory_lock = threading.Lock()


def get_authenticator_factory() -> AuthenticatorFactory:
    """Get the global AuthenticatorFactory instance."""
    global _factory_instance

    if _factory_instance is None:
        with _factory_lock:
            if _factory_instance is None:
                _factory_instance = AuthenticatorFactory()

    return _factory_instance
