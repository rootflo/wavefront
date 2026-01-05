"""
Function Node Adapter

Provides adapters to make registry functions compatible with function node signatures
without modifying the original function code.

Function nodes expect this signature:
    async def fn(
        inputs: List[BaseMessage] = None,
        variables: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> str:

Registry functions have their own signatures (e.g., async def bigquery_test_connection(datasource_id: str) -> str)

This adapter extracts parameters from inputs/variables and calls the original function.
"""

import json
import inspect
from types import FunctionType
from typing import List, Optional, Dict, Any, Callable, Awaitable
from flo_ai import BaseMessage
from flo_utils.utils.log import logger
from flo_ai import FloUtils


def extract_function_params(
    inputs: Optional[List[BaseMessage]] = None,
    variables: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Extract function parameters from inputs and variables.

    Parameters are extracted with this priority (higher priority overrides lower):
    1. kwargs (highest priority)
    2. variables dict
    3. inputs (lowest priority - extracted from last message as JSON)

    Args:
        inputs: List of BaseMessage objects, typically the last one contains function params
        variables: Dictionary of variables that may contain function parameters
        **kwargs: Additional keyword arguments (highest priority)

    Returns:
        Dictionary of extracted parameters
    """
    params = {}

    if inputs:
        last_input = inputs[-1]
        if hasattr(last_input, 'content') and isinstance(last_input.content, str):
            try:
                params.update(
                    FloUtils.extract_jsons_from_string(last_input.content, strict=True)
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                raise ValueError(
                    f'Invalid JSON: {last_input.content}. Function node input must be a JSON object.'
                )

    if variables:
        params.update(variables)

    params.update(kwargs)
    return params


def _build_call_kwargs(
    param_names: List[str],
    all_params: Dict[str, Any],
    kwargs: Dict[str, Any],
    excluded_params: set,
) -> Dict[str, Any]:
    """Build keyword arguments for calling the original function."""
    call_kwargs = {}
    for param_name in param_names:
        if param_name in excluded_params:
            continue
        if param_name in kwargs:
            call_kwargs[param_name] = kwargs[param_name]
        elif param_name in all_params:
            call_kwargs[param_name] = all_params[param_name]
    return call_kwargs


def _validate_required_params(
    sig: inspect.Signature,
    call_kwargs: Dict[str, Any],
    function_name: str,
    excluded_params: set,
) -> None:
    """Validate that all required parameters are present."""
    required_params = [
        param_name
        for param_name, param in sig.parameters.items()
        if param_name not in excluded_params
        and param.default == inspect.Parameter.empty
    ]

    missing_params = [param for param in required_params if param not in call_kwargs]
    if missing_params:
        error_msg = (
            f"Function '{function_name}' called with missing required parameters.\n"
            f'Missing parameters: {missing_params}.\n'
            f'Make sure last message contains all missing parameters as a JSON object.\n'
            f'Required parameters: {required_params}.\n'
            f'Provided parameters: {list(call_kwargs.keys())}.\n'
        )
        logger.error(error_msg)
        raise ValueError(error_msg)


def _convert_result_to_string(result: Any) -> str:
    """Convert function result to string."""
    if result is None:
        return ''
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list)):
        return json.dumps(result)
    return str(result)


def create_function_node_adapter(
    original_function: FunctionType,
    function_name: str,
) -> Callable[..., Awaitable[str]]:
    """
    Create an adapter function that wraps a registry function to work as a function node.

    The adapter:
    1. Accepts the function node signature (inputs, variables, **kwargs)
    2. Extracts parameters from inputs/variables
    3. Calls the original function with the extracted parameters
    4. Converts the result to a string

    Args:
        original_function: The original registry function to wrap
        function_name: Name of the function (for logging/error messages)

    Returns:
        An async function with the function node signature
    """
    sig = inspect.signature(original_function)
    param_names = list(sig.parameters.keys())
    excluded_params = {'inputs', 'variables'}
    is_async = inspect.iscoroutinefunction(original_function)

    async def adapted_function(
        inputs: Optional[List[BaseMessage]] = None,
        variables: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> str:
        """
        Adapted function that works as a function node.

        Args:
            inputs: List of BaseMessage objects containing function parameters
            variables: Dictionary of variables that may contain function parameters
            **kwargs: Additional keyword arguments

        Returns:
            String result of the function execution
        """
        try:
            all_params = extract_function_params(inputs, variables, **kwargs)
            call_kwargs = _build_call_kwargs(
                param_names, all_params, kwargs, excluded_params
            )
            _validate_required_params(sig, call_kwargs, function_name, excluded_params)

            result = (
                await original_function(**call_kwargs)
                if is_async
                else original_function(**call_kwargs)
            )
            return _convert_result_to_string(result)

        except ValueError:
            raise
        except Exception as e:
            error_msg = f"Error executing function '{function_name}': {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e

    adapted_function.__name__ = f'{original_function.__name__}_node_adapter'
    adapted_function.__doc__ = (
        f"Function node adapter for {function_name}.\n\n"
        f"Original function: {original_function.__name__}\n"
        f"Original docstring: {original_function.__doc__ or 'No docstring'}"
    )

    return adapted_function


def get_function_node_adapter(
    function_name: str,
    function_registry: Optional[Dict[str, FunctionType]] = None,
) -> Optional[Callable]:
    """
    Get a function node adapter for a function from the registry.

    Args:
        function_name: Name of the function in the registry
        function_registry: Optional custom registry dict. If None, uses FUNCTION_REGISTRY

    Returns:
        Adapted function with function node signature, or None if function not found
    """
    if function_registry is None:
        from tools_module.registry.function_registry import FUNCTION_REGISTRY

        function_registry = FUNCTION_REGISTRY

    original_function = function_registry.get(function_name)
    if original_function is None:
        logger.warning(f"Function '{function_name}' not found in registry")
        return None

    return create_function_node_adapter(original_function, function_name)
