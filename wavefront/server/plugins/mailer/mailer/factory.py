import dataclasses
import threading
from typing import Any, Dict, Optional, Type

from .gmail import GmailAppConfig, GmailProvider
from .outlook import OutlookAppConfig, OutlookProvider
from .types import EmailProviderABC, EmailProviderType

CONFIG_CLASSES = {
    EmailProviderType.GMAIL: GmailAppConfig,
    EmailProviderType.OUTLOOK: OutlookAppConfig,
}


def _assert_known_fields(config_class: Type[Any], config: Dict[str, Any]) -> None:
    allowed = {f.name for f in dataclasses.fields(config_class)}
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise ValueError(
            f'Unknown configuration fields: {", ".join(unknown)}. '
            f'Allowed: {", ".join(sorted(allowed))}'
        )


class EmailProviderFactory:
    """Builds and caches one provider instance per OAuth application.

    Instances are keyed by app id rather than by provider type so several apps
    of the same type can coexist, and so a config change only invalidates the
    app it belongs to.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(EmailProviderFactory, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._instances: Dict[str, EmailProviderABC] = {}
            self._instances_lock = threading.Lock()
            self._initialized = True

    def get_provider(
        self,
        app_id: str,
        provider_type: EmailProviderType,
        config: Dict[str, Any],
    ) -> EmailProviderABC:
        with self._instances_lock:
            cached = self._instances.get(app_id)
            if cached is not None:
                return cached

            provider = self._create_provider(provider_type, config)
            self._instances[app_id] = provider
            return provider

    def validate_config(
        self, provider_type: EmailProviderType, config: Dict[str, Any]
    ) -> bool:
        """Raises ValueError describing what is missing or unrecognised."""
        config_class = CONFIG_CLASSES.get(provider_type)
        if config_class is None:
            raise ValueError(f'Unsupported email provider: {provider_type}')

        _assert_known_fields(config_class, config)

        for field_name in config_class.required_fields():
            if not config.get(field_name):
                raise ValueError(f'{field_name} is required')

        try:
            config_class(**config)
        except TypeError as exc:
            raise ValueError(f'Invalid {provider_type} configuration: {exc}') from exc

        return True

    def update_provider(
        self,
        app_id: str,
        provider_type: EmailProviderType,
        config: Dict[str, Any],
    ) -> EmailProviderABC:
        """Rebuild an app's provider after its configuration changed.

        Validation runs before the lock so a rejected config leaves the cached
        instance untouched.
        """
        self.validate_config(provider_type, config)

        with self._instances_lock:
            provider = self._create_provider(provider_type, config)
            self._instances[app_id] = provider
            return provider

    def remove_provider(self, app_id: str) -> bool:
        with self._instances_lock:
            return self._instances.pop(app_id, None) is not None

    def clear_all_instances(self) -> None:
        with self._instances_lock:
            self._instances.clear()

    def get_cached_instance_count(self) -> int:
        with self._instances_lock:
            return len(self._instances)

    def _create_provider(
        self, provider_type: EmailProviderType, config: Dict[str, Any]
    ) -> EmailProviderABC:
        self.validate_config(provider_type, config)
        if provider_type == EmailProviderType.GMAIL:
            return GmailProvider(GmailAppConfig(**config))
        if provider_type == EmailProviderType.OUTLOOK:
            return OutlookProvider(OutlookAppConfig(**config))
        raise ValueError(f'Unsupported email provider: {provider_type}')


_factory_instance: Optional[EmailProviderFactory] = None
_factory_lock = threading.Lock()


def get_email_provider_factory() -> EmailProviderFactory:
    """Get the global EmailProviderFactory instance."""
    global _factory_instance

    if _factory_instance is None:
        with _factory_lock:
            if _factory_instance is None:
                _factory_instance = EmailProviderFactory()
            return _factory_instance

    return _factory_instance
