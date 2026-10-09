"""
Main Function Registry

Aggregates all function registries from different categories into a single registry
for use by the ToolLoader.
"""

from typing import Callable, Dict

from tools_module.floware_api import FlowareApiClient
from tools_module.registry.registries.api_service_registry import (
    API_SERVICE_REGISTRY,
)
from tools_module.registry.registries.configuration_registry import (
    build_configuration_registry,
)
from tools_module.registry.registries.datasource_registry import (
    build_datasource_registry,
)
from tools_module.registry.registries.email_registry import build_email_registry
from tools_module.registry.registries.message_processor_registry import (
    build_message_processor_registry,
)
from tools_module.registry.registries.util_function_registry import (
    build_util_function_registry,
)


# TODO: Import other category registries as they are implemented


def _merge_registries(*registries):
    """Merge registries with collision detection"""
    merged = {}
    for registry in registries:
        for key, value in registry.items():
            if key in merged:
                raise ValueError(
                    f"Duplicate function name '{key}' found across registries"
                )
            merged[key] = value
    return merged


def build_function_registry(api: FlowareApiClient) -> Dict[str, Callable]:
    """Build the master registry, binding every floware-calling tool to ``api``."""
    return _merge_registries(
        build_datasource_registry(api),
        build_email_registry(api),
        build_util_function_registry(api),
        build_message_processor_registry(api),
        API_SERVICE_REGISTRY,
        build_configuration_registry(api),
    )
