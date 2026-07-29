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

Registry functions have their own signatures (e.g., async def datasource_insert_rows(datasource_id: str, table_name: str, data, single_row: bool = False) -> str)

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
    3. inputs (lowest priority - every message parsed as JSON, in order, last wins)

    Every message in ``inputs`` is parsed, not just the last one: a node with
    ``input_filter: [a, b]`` is handed both nodes' outputs, and reading only the
    last would silently discard the rest. Two extra keys are added for nodes that
    need to tell those outputs apart:

    - ``node_outputs``: ``{producing_node_name: [parsed, ...]}``. List-valued
      because a ForEach with ``forward_all_results`` emits N results all tagged
      with the ForEach node's own name. Requires the ``metadata['node']`` tag
      that ``MessageMemoryItem`` stamps onto each message.
    - ``input_list``: the same parsed payloads in execution order.

    The flat merge is kept so existing function nodes are unaffected — they read
    their arguments straight out of the upstream node's JSON, and because the
    merge iterates in order with last-wins, a single-input node produces exactly
    the same params as before.

    Args:
        inputs: List of BaseMessage objects carrying function params as JSON
        variables: Dictionary of variables that may contain function parameters
        **kwargs: Additional keyword arguments (highest priority)

    Returns:
        Dictionary of extracted parameters
    """
    params = {}

    if inputs:
        by_node: Dict[str, List[Any]] = {}
        ordered: List[Any] = []

        last_index = len(inputs) - 1

        # The last message is the one the node is contractually fed, so anything
        # that stops it being read has to fail loudly — proceeding would call the
        # function with only the earlier messages' params, i.e. on stale or empty
        # data, and surface as a confusing error somewhere further in. Earlier
        # messages may legitimately be unreadable now that a wider input_filter
        # can select the raw workflow inputs (e.g. an uploaded document, whose
        # content is a DocumentMessageContent rather than text), which were never
        # looked at before; those are skipped.
        for index, message in enumerate(inputs):
            content = getattr(message, 'content', None)

            if not isinstance(content, str):
                if index == last_index:
                    raise ValueError(
                        f'Function node input must be a JSON object, but the last '
                        f'input has content of type {type(content).__name__}.'
                    )
                continue

            try:
                parsed = FloUtils.extract_jsons_from_string(content, strict=True)
            except (json.JSONDecodeError, TypeError, ValueError):
                if index == last_index:
                    raise ValueError(
                        f'Invalid JSON: {content}. Function node input must be a JSON object.'
                    )
                continue

            ordered.append(parsed)
            producing_node = (getattr(message, 'metadata', None) or {}).get('node')
            if producing_node:
                by_node.setdefault(producing_node, []).append(parsed)

        for parsed in ordered:
            params.update(parsed)

        params['node_outputs'] = by_node
        params['input_list'] = ordered

    if variables:
        params.update(variables)

    params.update(kwargs)
    return params


def _build_call_kwargs(
    param_names: List[str],
    all_params: Dict[str, Any],
    kwargs: Dict[str, Any],
    excluded_params: set,
    accepts_var_keyword: bool = False,
) -> Dict[str, Any]:
    """Build keyword arguments for calling the original function.

    Only parameters the signature names are forwarded, unless the function
    declares ``**kwargs`` — those take arbitrary dynamic parameters (the message
    processor and API service tools build their payload from whatever they are
    given), so everything else collected is passed through to them as well.
    """
    call_kwargs = {}
    for param_name in param_names:
        if param_name in excluded_params:
            continue
        if param_name in kwargs:
            call_kwargs[param_name] = kwargs[param_name]
        elif param_name in all_params:
            call_kwargs[param_name] = all_params[param_name]

    if accepts_var_keyword:
        for param_name, value in all_params.items():
            if param_name in excluded_params:
                continue
            call_kwargs.setdefault(param_name, value)

    return call_kwargs


def _validate_required_params(
    sig: inspect.Signature,
    call_kwargs: Dict[str, Any],
    function_name: str,
    excluded_params: set,
) -> None:
    """Validate that all required parameters are present.

    Variadic parameters (``*args`` / ``**kwargs``) report no default, so they
    would otherwise be reported as missing required arguments — they are not,
    they simply collect whatever else is passed.
    """
    variadic = (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
    required_params = [
        param_name
        for param_name, param in sig.parameters.items()
        if param_name not in excluded_params
        and param.kind not in variadic
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
    accepts_var_keyword = any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values()
    )

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
                param_names,
                all_params,
                kwargs,
                excluded_params,
                accepts_var_keyword,
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
