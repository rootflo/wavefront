from typing import Dict

from .base import TriggerProvider


class UnsupportedTriggerProvider(Exception):
    pass


class TriggerProviderRegistry:
    def __init__(self) -> None:
        self._providers: Dict[str, TriggerProvider] = {}

    def register(self, provider: TriggerProvider) -> None:
        if not provider.provider_type:
            raise ValueError('provider.provider_type must be set')
        self._providers[provider.provider_type] = provider

    def get(self, provider_type: str) -> TriggerProvider:
        try:
            return self._providers[provider_type]
        except KeyError:
            raise UnsupportedTriggerProvider(
                f'No trigger provider registered for type: {provider_type}'
            )

    def has(self, provider_type: str) -> bool:
        return provider_type in self._providers
