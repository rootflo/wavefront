"""
Function Node Registry

Provides function node-compatible versions of all registry functions.
These functions can be used directly as function nodes in workflows without
modifying the original registry functions.

Usage:
    from tools_module.registry.function_node_registry import FUNCTION_NODE_REGISTRY

    # Get an adapted function
    adapted_fn = FUNCTION_NODE_REGISTRY.get('bigquery_test_connection')

    # Use it as a function node
    result = await adapted_fn(
        inputs=[...],
        variables={'datasource_id': 'my-datasource'},
    )
"""

from typing import Dict, Callable, Optional
from tools_module.registry.function_registry import FUNCTION_REGISTRY
from tools_module.registry.function_node_adapter import create_function_node_adapter


def _create_function_node_registry() -> Dict[str, Callable]:
    """
    Create a registry of function node adapters for all registry functions.

    Returns:
        Dictionary mapping function names to their adapted versions
    """
    node_registry = {}

    for function_name, original_function in FUNCTION_REGISTRY.items():
        adapted_function = create_function_node_adapter(
            original_function,
            function_name,
        )
        node_registry[function_name] = adapted_function

    return node_registry


# Registry of function node-compatible functions
FUNCTION_NODE_REGISTRY = _create_function_node_registry()


def get_function_node(function_name: str) -> Optional[Callable]:
    """
    Get a function node adapter for a specific function.

    Args:
        function_name: Name of the function

    Returns:
        Adapted function with function node signature, or None if not found
    """
    return FUNCTION_NODE_REGISTRY.get(function_name)


def get_all_function_node_names() -> list[str]:
    """
    Get list of all available function node names.

    Returns:
        List of function names available as function nodes
    """
    return list(FUNCTION_NODE_REGISTRY.keys())
