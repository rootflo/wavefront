"""
Utility functions for agent operations
"""


def get_agent_yaml_key(namespace: str, agent_name: str) -> str:
    """
    Generate the YAML storage key for an agent

    Args:
        namespace: The namespace of the agent
        agent_name: The unique identifier for the agent

    Returns:
        str: The storage key for the agent YAML file
    """
    return f'agents/{namespace}/{agent_name}.yaml'


def get_agent_prefix(namespace: str = None) -> str:
    """
    Generate the storage prefix for listing agents

    Args:
        namespace: Optional namespace to filter agents. If None, returns prefix for all agents

    Returns:
        str: The storage prefix for listing agents
    """
    if namespace:
        return f'agents/{namespace}/'
    return 'agents/'
