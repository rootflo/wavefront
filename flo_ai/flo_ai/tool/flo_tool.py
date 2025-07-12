import inspect
import asyncio
from typing import Dict, Any, Callable, Optional, Union
from functools import wraps
from .base_tool import Tool


def flo_tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameter_descriptions: Optional[Dict[str, str]] = None,
):
    """
    Decorator to automatically convert a function into a Tool object.

    Args:
        name: Optional custom name for the tool. If not provided, uses function name.
        description: Optional description for the tool. If not provided, uses function docstring.
        parameter_descriptions: Optional dict mapping parameter names to their descriptions.
                               If not provided, will try to extract from docstring or use defaults.

    Example:
        @flo_tool(
            description="Calculate mathematical operations",
            parameter_descriptions={
                "operation": "The operation to perform (add, subtract, multiply, divide)",
                "x": "First number",
                "y": "Second number"
            }
        )
        async def calculate(operation: str, x: float, y: float) -> float:
            # function implementation
            pass

        # The function can be used normally
        result = await calculate("add", 5, 3)

        # And you can get the Tool object
        tool = calculate.tool
    """

    def decorator(func: Callable) -> Callable:
        # Create the Tool object
        tool = _create_tool_from_function(
            func, name, description, parameter_descriptions
        )

        # Attach the tool to the function
        func.tool = tool

        # Return the original function (wrapped to preserve async behavior)
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        # Return appropriate wrapper based on whether function is async
        if asyncio.iscoroutinefunction(func):
            async_wrapper.tool = tool
            return async_wrapper
        else:
            sync_wrapper.tool = tool
            return sync_wrapper

    return decorator


def _create_tool_from_function(
    func: Callable,
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameter_descriptions: Optional[Dict[str, str]] = None,
) -> Tool:
    """Create a Tool object from a function."""
    # Get function signature
    sig = inspect.signature(func)

    # Determine tool name
    tool_name = name or func.__name__

    # Determine tool description
    tool_description = description or func.__doc__ or f'Tool for {func.__name__}'

    # Extract parameters
    parameters = {}
    for param_name, param in sig.parameters.items():
        # Skip self parameter for methods
        if param_name == 'self':
            continue

        param_type = param.annotation
        param_default = param.default

        # Determine if parameter is required
        is_required = param.default == inspect.Parameter.empty

        # Get parameter description
        param_desc = None
        if parameter_descriptions and param_name in parameter_descriptions:
            param_desc = parameter_descriptions[param_name]
        else:
            # Try to extract from docstring
            param_desc = _extract_param_description_from_docstring(func, param_name)

        # Default description if none found
        if not param_desc:
            param_desc = f'Parameter {param_name}'

        # Determine JSON schema type
        json_type = _get_json_type(param_type)

        parameters[param_name] = {
            'type': json_type,
            'description': param_desc,
            'required': is_required,
        }

        # Add default value if present
        if not is_required:
            parameters[param_name]['default'] = param_default

    # Create the tool
    return Tool(
        name=tool_name,
        description=tool_description,
        function=func,
        parameters=parameters,
    )


def _extract_param_description_from_docstring(
    func: Callable, param_name: str
) -> Optional[str]:
    """Extract parameter description from function docstring."""
    if not func.__doc__:
        return None

    doc_lines = func.__doc__.split('\n')
    for line in doc_lines:
        line = line.strip()
        if line.startswith(f':param {param_name}:'):
            return line.split(':', 2)[2].strip()
        elif line.startswith('Args:') and f'{param_name}:' in line:
            # Handle Google-style docstrings
            parts = line.split(f'{param_name}:', 1)
            if len(parts) > 1:
                return parts[1].strip()

    return None


def _get_json_type(python_type: Any) -> str:
    """Convert Python type to JSON schema type."""
    if python_type == inspect.Parameter.empty:
        return 'string'  # Default to string if no type annotation

    # Handle Union types (e.g., Optional[str] -> str)
    if hasattr(python_type, '__origin__') and python_type.__origin__ is Union:
        # For Optional types, get the first non-None type
        args = python_type.__args__
        non_none_types = [arg for arg in args if arg is not type(None)]
        if non_none_types:
            python_type = non_none_types[0]

    # Handle basic types
    type_mapping = {
        str: 'string',
        int: 'integer',
        float: 'number',
        bool: 'boolean',
        list: 'array',
        dict: 'object',
    }

    # Check for exact type matches
    if python_type in type_mapping:
        return type_mapping[python_type]

    # Check for isinstance relationships
    for py_type, json_type in type_mapping.items():
        try:
            if issubclass(python_type, py_type):
                return json_type
        except TypeError:
            continue

    # Default to string for unknown types
    return 'string'


# Convenience function for creating tools from existing functions
def create_tool_from_function(
    func: Callable,
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameter_descriptions: Optional[Dict[str, str]] = None,
) -> Tool:
    """
    Create a Tool from an existing function without using the decorator.

    Args:
        func: The function to convert to a tool
        name: Optional custom name for the tool
        description: Optional description for the tool
        parameter_descriptions: Optional parameter descriptions

    Returns:
        Tool: The created tool object
    """
    return _create_tool_from_function(func, name, description, parameter_descriptions)
