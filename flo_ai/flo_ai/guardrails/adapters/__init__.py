"""Safety provider adapters.

Each concrete adapter is resolved on first attribute access rather than at
import time. Both pull heavy optional dependencies — Presidio brings spaCy and
a language model — and a deployment should only pay for the providers its
policy actually names.
"""

from typing import Any

from .base_adapter import BaseAdapter

__all__ = ['AzureContentSafetyAdapter', 'BaseAdapter', 'PresidioAdapter']

_LAZY = {
    'AzureContentSafetyAdapter': ('.azure_adapter', 'AzureContentSafetyAdapter'),
    'PresidioAdapter': ('.presidio_adapter', 'PresidioAdapter'),
}


def __getattr__(name: str) -> Any:
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')

    from importlib import import_module

    module = import_module(target[0], __name__)
    value = getattr(module, target[1])
    globals()[name] = value
    return value


def __dir__() -> list:
    return sorted(__all__)
