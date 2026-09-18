import re


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
