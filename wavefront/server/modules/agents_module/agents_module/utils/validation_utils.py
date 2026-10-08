import re
from typing import Any, Dict, List, Optional, Union

from agents_module.utils.mime_type_utils import (
    MAX_FILE_NAME_LENGTH,
    file_name_safety_issue,
)

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
    if value is None or isinstance(value, bool):
        return

    if isinstance(value, (int, float)):
        # A JSON number sidesteps the string length cap: the parser accepts
        # integers up to 4300 digits, so `{"n": 999…}` puts 4300 characters
        # into the prompt where the same digits in quotes stop at 500. Digits
        # are inside the value charset, so quoting is the only difference.
        # Measure the serialized form, which is what reaches the prompt.
        #
        # str() on an integer past the parser's own ceiling raises ValueError,
        # which is what this function raises anyway — a direct caller with an
        # absurd int still gets a clean rejection rather than a crash.
        rendered = str(value)
        if len(rendered) > MAX_VARIABLE_VALUE_LENGTH:
            raise ValueError(
                f'Variable value too long{_describe(location)}: '
                f'{len(rendered)} characters, limit is {MAX_VARIABLE_VALUE_LENGTH}.'
            )
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


def validate_variable_filters(filters: Dict[str, str]) -> Dict[str, str]:
    """Hold variable *filter* keys and values to the rules the stored ones obey.

    Symmetry with validate_inference_variables is the point: a filter that could
    never have been stored can never match either, so rejecting it outright is
    clearer to the caller than an empty page that looks like a real answer.

    MAX_VARIABLE_COUNT does double duty here. On the write side it bounds prompt
    size; on the read side it bounds how many AND terms one request can put into
    the query.

    Values always arrive as strings, having come off the query string, so only
    the string branch of the value check is ever exercised.
    """
    if not filters:
        return filters

    _check_count(len(filters), 'variable filters')

    for key, value in filters.items():
        _validate_variable_key(key)
        _validate_variable_value(value, key)

    return filters


# Allowlist of keys an input item and its `content` object may carry; anything
# not enumerated here is refused at the boundary. The content set is the union of
# the media keys the backend reads (is_image_message / is_doc_message) and the
# descriptive fields the client sends (image_type / document_type / metadata).
# All but `metadata` are dropped downstream, so only `metadata` is validated
# further.
_ALLOWED_INPUT_ITEM_KEYS = frozenset({'role', 'content'})
_ALLOWED_INPUT_ROLES = frozenset({'user', 'assistant'})
_ALLOWED_CONTENT_KEYS = frozenset(
    {
        'image_base64',
        'image_url',
        'image_bytes',
        'image_file_path',
        'image_type',
        'document_base64',
        'document_url',
        'document_bytes',
        'document_file_path',
        'document_type',
        'mime_type',
        'file_name',
        'metadata',
    }
)
# `metadata` is an expected passthrough object, but only these descriptive fields
# are allowed inside it. Any other, free-form key is refused so a script or other
# payload cannot ride in one.
_ALLOWED_METADATA_KEYS = frozenset({'filename', 'size'})


def _validate_input_metadata(metadata: Any, location: str) -> None:
    if not isinstance(metadata, dict):
        raise ValueError(
            f'Invalid input{_describe(location)}: metadata must be an object.'
        )

    if not set(metadata).issubset(_ALLOWED_METADATA_KEYS):
        # Name the allowed fields — they are our own static constants, so this
        # states the contract without echoing the caller's unexpected key.
        allowed = ', '.join(f"'{key}'" for key in sorted(_ALLOWED_METADATA_KEYS))
        raise ValueError(
            f'Invalid input{_describe(location)}: metadata may only contain '
            f'{allowed}.'
        )

    # The exact same rule the file-name gate enforces (ensure_safe_file_name),
    # via the one shared classifier — this value is displayed like a file name
    # and must get the same XSS-safe treatment without the two drifting.
    issue = file_name_safety_issue(metadata.get('filename'))
    if issue == 'type':
        raise ValueError(
            f'Invalid input{_describe(location)}: metadata filename must be a '
            'string.'
        )
    if issue == 'length':
        raise ValueError(
            f'Invalid input{_describe(location)}: metadata filename too long, '
            f'limit is {MAX_FILE_NAME_LENGTH} characters.'
        )
    if issue == 'charset':
        raise ValueError(
            f'Invalid input{_describe(location)}: metadata filename contains '
            'unsupported characters.'
        )

    # Must be numeric — a byte count — and never negative. bool is an int
    # subclass, so it is excluded explicitly rather than sneaking through.
    size = metadata.get('size')
    if size is not None and (
        isinstance(size, bool) or not isinstance(size, int) or size < 0
    ):
        raise ValueError(
            f'Invalid input{_describe(location)}: metadata size must be a '
            'non-negative integer.'
        )


def _validate_input_content(content: Any, location: str) -> None:
    # Text content is a bare string and has no key surface to constrain; only an
    # object (a media message) does.
    if not isinstance(content, dict):
        return

    if not set(content).issubset(_ALLOWED_CONTENT_KEYS):
        raise ValueError(
            f'Invalid input{_describe(location)}: unexpected field in content.'
        )

    if 'metadata' in content:
        _validate_input_metadata(content['metadata'], location)


def validate_inference_inputs(
    inputs: Union[List[Union[dict, str]], str, None],
) -> Union[List[Union[dict, str]], str, None]:
    """Hold an inference request's `inputs` to a known set of fields.

    Each item, its `content` object and its `metadata` object are checked against
    an explicit key allowlist so an unvalidated field cannot cross the boundary.
    The offending value is otherwise dropped further down the pipeline, so this
    only turns silent acceptance into an explicit rejection — no behaviour changes
    for a well-formed request.

    The message stays generic and index-located: this validator never puts the
    untrusted key or value into the error text. (FastAPI's default 422 still
    echoes the raw input separately, in pydantic's `input` field — that is the
    framework's doing, not this validator's.)

    Returns `inputs` unchanged so it can be used as a pydantic field validator.
    """
    if inputs is None or isinstance(inputs, str):
        return inputs

    for index, item in enumerate(inputs):
        location = f'index {index}'

        if isinstance(item, str):
            continue

        if not isinstance(item, dict):
            raise ValueError(
                f'Invalid input{_describe(location)}: must be a string or an ' 'object.'
            )

        if not set(item).issubset(_ALLOWED_INPUT_ITEM_KEYS):
            raise ValueError(f'Invalid input{_describe(location)}: unexpected field.')

        role = item.get('role')
        if role is not None and (
            not isinstance(role, str) or role not in _ALLOWED_INPUT_ROLES
        ):
            raise ValueError(
                f'Invalid input{_describe(location)}: role must be '
                "'user' or 'assistant'."
            )

        _validate_input_content(item.get('content'), location)

    return inputs


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
