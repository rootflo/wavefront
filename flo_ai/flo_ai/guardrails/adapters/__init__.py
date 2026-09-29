"""Safety provider adapters.

Each concrete adapter is resolved on first attribute access rather than at
import time. Both pull heavy optional dependencies — Presidio brings spaCy and
a language model — and a deployment should only pay for the providers its
policy actually names.
"""

from typing import TYPE_CHECKING, Any

from .base_adapter import BaseAdapter

if TYPE_CHECKING:
    from .azure_adapter import AzureContentSafetyAdapter
    from .presidio_adapter import PresidioAdapter
    from .pii_catalog import (
        ENTITY_CATALOG,
        EntityMeta,
        describe as describe_entity,
        group_sort_key,
    )

__all__ = [
    'AzureContentSafetyAdapter',
    'BaseAdapter',
    'ENTITY_CATALOG',
    'EntityMeta',
    'PresidioAdapter',
    'describe_entity',
    'group_sort_key',
]

_LAZY = {
    'AzureContentSafetyAdapter': ('.azure_adapter', 'AzureContentSafetyAdapter'),
    'PresidioAdapter': ('.presidio_adapter', 'PresidioAdapter'),
    # Presentation metadata only - no Presidio import, so this is cheap. Listed
    # here so callers have one import path for everything adapter-related.
    'ENTITY_CATALOG': ('.pii_catalog', 'ENTITY_CATALOG'),
    'EntityMeta': ('.pii_catalog', 'EntityMeta'),
    'describe_entity': ('.pii_catalog', 'describe'),
    'group_sort_key': ('.pii_catalog', 'group_sort_key'),
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
