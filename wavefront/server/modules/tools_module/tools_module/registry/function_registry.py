"""
Main Function Registry

Aggregates all function registries from different categories into a single registry
for use by the ToolLoader.
"""

from tools_module.registry.registries.datasource_registry import DATASOURCE_REGISTRY
from tools_module.registry.registries.knowledge_base_registry import (
    KNOWLEDGE_BASE_REGISTRY,
)
from tools_module.registry.registries.email_registry import EMAIL_REGISTRY
from tools_module.registry.registries.util_function_registry import (
    UTIL_FUNCTION_REGISTRY,
)
from tools_module.registry.registries.message_processor_registry import (
    MESSAGE_PROCESSOR_REGISTRY,
)
from tools_module.registry.registries.api_service_registry import (
    API_SERVICE_REGISTRY,
)


# TODO: Import other category registries as they are implemented
# Master registry combining all function categories


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


FUNCTION_REGISTRY = _merge_registries(
    DATASOURCE_REGISTRY,
    KNOWLEDGE_BASE_REGISTRY,
    EMAIL_REGISTRY,
    UTIL_FUNCTION_REGISTRY,
    MESSAGE_PROCESSOR_REGISTRY,
    API_SERVICE_REGISTRY,
)


# Helper function to get all available function names
def get_available_function_names():
    """Get list of all available function names"""
    return list(FUNCTION_REGISTRY.keys())
