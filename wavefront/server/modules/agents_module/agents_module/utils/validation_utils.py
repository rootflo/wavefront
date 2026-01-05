import re


def validate_agent_workflow_name(name: str, type: str = 'agent') -> None:
    """
    Validate agent or workflow name to ensure it:
    - Starts with a letter (a-z, A-Z)
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

    # Must start with a letter, followed by letters, numbers, hyphens, or underscores
    pattern = r'^[a-zA-Z][a-zA-Z0-9_-]*$'

    if not re.match(pattern, name):
        raise ValueError(
            f'{type.capitalize()} name must start with a letter and can only contain letters, numbers, '
            'hyphens, and underscores. Spaces and special characters are not allowed.'
        )
