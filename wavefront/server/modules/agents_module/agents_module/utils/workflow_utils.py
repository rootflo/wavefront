"""
Utility functions for workflow operations
"""


def get_workflow_yaml_key(namespace: str, workflow_name: str) -> str:
    """
    Generate the YAML storage key for a workflow

    Args:
        namespace: The namespace of the workflow
        workflow_name: The unique identifier for the workflow

    Returns:
        str: The storage key for the workflow YAML file
    """
    return f'workflows/{namespace}/{workflow_name}.yaml'


def get_workflow_id_and_namespace_from_yaml_key(yaml_key: str) -> tuple[str, str]:
    """
    Get the workflow ID and namespace from the YAML key

    Args:
        yaml_key: The YAML key

    Returns:
        tuple[str, str]: The workflow ID and namespace
    """
    parts = yaml_key.split('/')
    if len(parts) >= 3:
        return parts[1], parts[2].replace('.yaml', '')
    return None, None


def get_workflow_prefix(namespace: str = None) -> str:
    """
    Generate the storage prefix for listing workflows

    Args:
        namespace: Optional namespace to filter workflows. If None, returns prefix for all workflows

    Returns:
        str: The storage prefix for listing workflows
    """
    if namespace:
        return f'workflows/{namespace}/'
    return 'workflows/'
