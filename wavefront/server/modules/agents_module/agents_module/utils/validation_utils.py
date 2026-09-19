import re
from typing import Any, Dict, Optional

# Inference variables are substituted into agent prompts, so the characters they
# may carry are restricted. Values also allow spaces, since a variable
# legitimately holds prose — a sentence to translate, a tone description —
# whereas a variable *name* never needs one.
#
# Both are anchored with \Z rather than $ for the same reason as the name
# pattern below: Python's $ also matches just before a trailing newline, so
# `value\n` would otherwise pass and reach the prompt with the newline intact.
VARIABLE_VALUE_PATTERN = r'^[a-zA-Z0-9_/ -]*\Z'
VARIABLE_KEY_PATTERN = r'^[a-zA-Z0-9_/-]+\Z'

# The character set bounds what a variable may contain, not how much of it.
# Without a length cap a single variable can still inflate the prompt — and the
# token bill — without limit. Names are identifiers, so 64 is already generous;
# values are prompt fragments.
MAX_VARIABLE_KEY_LENGTH = 64
MAX_VARIABLE_VALUE_LENGTH = 500

# ...and a per-variable cap still leaves the *number* of them unbounded, so a
# payload of legal variables can be arbitrarily large in aggregate. Applied to
# nested objects and lists as well: capping only the top level would be
# bypassed by moving the bulk one level down.
MAX_VARIABLE_COUNT = 10

_VALUE_CHARSET_DESCRIPTION = (
    'only letters, numbers, spaces, hyphens, underscores and slashes are allowed'
)
_KEY_CHARSET_DESCRIPTION = (
    'only letters, numbers, hyphens, underscores and slashes are allowed'
)

# Scalars carry no characters to constrain — a bool or a number cannot smuggle
# anything into a prompt — so they pass without a pattern check.
_ALLOWED_SCALAR_TYPES = (bool, int, float)


def _describe(location: str) -> str:
    return f' at {location}' if location else ''


def _check_count(size: int, noun: str, location: str = '') -> None:
    if size > MAX_VARIABLE_COUNT:
        raise ValueError(
            f'Too many {noun}{_describe(location)}: '
            f'{size}, limit is {MAX_VARIABLE_COUNT}.'
        )


def _validate_variable_value(value: Any, location: str) -> None:
    """Check one variable value, recursing through lists and nested objects."""
    if value is None or isinstance(value, _ALLOWED_SCALAR_TYPES):
        return

    if isinstance(value, str):
        # Length first: a clearer error for an oversized value than a charset
        # complaint, and it keeps the regex off a very long string.
        if len(value) > MAX_VARIABLE_VALUE_LENGTH:
            raise ValueError(
                f'Variable value too long{_describe(location)}: '
                f'{len(value)} characters, limit is {MAX_VARIABLE_VALUE_LENGTH}.'
            )
        if not re.match(VARIABLE_VALUE_PATTERN, value):
            raise ValueError(
                f'Invalid variable value{_describe(location)}: '
                f'{_VALUE_CHARSET_DESCRIPTION}.'
            )
        return

    if isinstance(value, (list, tuple)):
        _check_count(len(value), 'items', location)
        for index, item in enumerate(value):
            _validate_variable_value(item, f'{location}[{index}]')
        return

    if isinstance(value, dict):
        _check_count(len(value), 'entries', location)
        for nested_key, nested_value in value.items():
            _validate_variable_key(nested_key, location)
            _validate_variable_value(nested_value, f'{location}.{nested_key}')
        return

    raise ValueError(
        f'Unsupported variable value type{_describe(location)}: '
        f'{type(value).__name__}'
    )


def _validate_variable_key(key: Any, location: str = '') -> None:
    if not isinstance(key, str):
        raise ValueError(
            f'Variable names must be strings{_describe(location)}, '
            f'got {type(key).__name__}'
        )
    if len(key) > MAX_VARIABLE_KEY_LENGTH:
        raise ValueError(
            f'Variable name too long{_describe(location)}: '
            f'{len(key)} characters, limit is {MAX_VARIABLE_KEY_LENGTH}.'
        )
    if not re.match(VARIABLE_KEY_PATTERN, key):
        raise ValueError(
            f'Invalid variable name `{key}`{_describe(location)}: '
            f'{_KEY_CHARSET_DESCRIPTION}, and it cannot be empty.'
        )


def validate_inference_variables(
    variables: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Restrict inference variable names and values by character set and length.

    Variables are the one caller-controlled channel that reaches an agent
    prompt — `{var}` placeholders resolve from this dict — so both the names and
    the values are held to VARIABLE_KEY_PATTERN / VARIABLE_VALUE_PATTERN, and to
    MAX_VARIABLE_KEY_LENGTH / MAX_VARIABLE_VALUE_LENGTH. MAX_VARIABLE_COUNT
    bounds how many there may be.

    Nested lists and objects are walked to the leaves, so none of the three —
    a disallowed character, an oversized string, or bulk by sheer count — can
    be smuggled in one level down.

    Returns the dict unchanged so it can be used as a pydantic field validator.
    """
    if variables is None:
        return variables

    _check_count(len(variables), 'variables')

    for key, value in variables.items():
        _validate_variable_key(key)
        _validate_variable_value(value, key)

    return variables


def validate_agent_workflow_name(name: str, type: str = 'agent') -> None:
    """
    Validate agent or workflow name to ensure it:
    - Starts with a letter or number (a-z, A-Z, 0-9)
    - Contains only letters, numbers, hyphens, and underscores
    - No spaces or special characters

    Args:
        name: The name to validate
        type: Type of entity ('agent' or 'workflow') for error messages

    Raises:
        ValueError: If the name contains invalid characters or format
    """
    if not name:
        raise ValueError(f'{type.capitalize()} name cannot be empty')

    # Must start with a letter or number, followed by letters, numbers, hyphens, or underscores.
    # Anchored with \Z, not $: Python's $ also matches just before a trailing
    # newline, so `my-agent\n` passed and then went straight into the cloud
    # storage key agents/{namespace}/{name}/{version}.yaml.
    pattern = r'^[a-zA-Z0-9][a-zA-Z0-9_-]*\Z'

    if not re.match(pattern, name):
        raise ValueError(
            f'{type.capitalize()} name must start with a letter or number and can only contain letters, numbers, '
            'hyphens, and underscores. Spaces and special characters are not allowed.'
        )
