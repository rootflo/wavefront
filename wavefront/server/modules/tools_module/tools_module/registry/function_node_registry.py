"""
Function Node Registry

Provides function node-compatible versions of all registry functions.
These functions can be used directly as function nodes in workflows without
modifying the original registry functions.

Usage:
    node_registry = build_function_node_registry(function_registry)

    # Get an adapted function
    adapted_fn = node_registry.get('datasource_insert_rows')

    # Use it as a function node
    result = await adapted_fn(
        inputs=[...],
        variables={'datasource_id': 'my-datasource'},
    )
"""

from typing import Callable, Dict, Mapping

from tools_module.registry.function_node_adapter import create_function_node_adapter


def build_function_node_registry(
    function_registry: Mapping[str, Callable],
) -> Dict[str, Callable]:
    """
    Create a registry of function node adapters for all registry functions.

    Args:
        function_registry: The (already bound) registry to adapt

    Returns:
        Dictionary mapping function names to their adapted versions
    """
    return {
        function_name: create_function_node_adapter(original_function, function_name)
        for function_name, original_function in function_registry.items()
    }
