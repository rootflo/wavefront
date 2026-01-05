"""Helper functions for YAML validation error formatting."""

from typing import Dict, Any, Tuple


def format_validation_error_path(loc: Tuple, config: Dict[str, Any]) -> str:
    """Format error location path, using section names instead of indices when available.

    This function improves error message readability by replacing numeric indices
    with meaningful section names (e.g., agent names, router names) when available
    in the YAML configuration.

    Args:
        loc: Location tuple from Pydantic validation error (e.g., ('arium', 'agents', 0, 'name'))
        config: Original YAML configuration dictionary

    Returns:
        Formatted path string with names instead of indices where possible

    Example:
        Instead of: "arium -> agents -> 0 -> job: Field required"
        Returns: "arium -> agents -> my_agent -> job: Field required"
    """
    path_parts = []
    current = config

    for part in loc:
        # If part is an integer, try to find the name of the item at that index
        if isinstance(part, int):
            # Check if current is a list and we can access the item
            if isinstance(current, list) and 0 <= part < len(current):
                item = current[part]
                # If the item has a 'name' field, use that instead of the index
                if isinstance(item, dict) and 'name' in item:
                    path_parts.append(f"{item['name']}")
                else:
                    path_parts.append(str(part))
                current = item
            else:
                path_parts.append(str(part))
        else:
            # String key - use it directly
            path_parts.append(str(part))
            # Navigate deeper into the config
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list):
                # If we're at a list level, we can't navigate further by key
                current = None
            else:
                current = None

    return ' -> '.join(path_parts)
