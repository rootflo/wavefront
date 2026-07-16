from typing import Optional
from uuid import UUID


def get_agent_by_id_cache_key(agent_id: UUID) -> str:
    """Get cache key for agent metadata by ID"""
    return f'agent:id:{agent_id}'


def get_agent_yaml_cache_key(namespace: str, agent_name: str, version: int) -> str:
    """Get cache key for a specific version of an agent's YAML content"""
    return f'agent_yaml:{namespace}:{agent_name}:{version}'


def get_agent_current_version_cache_key(namespace: str, agent_name: str) -> str:
    """
    Get cache key for an agent's current_version, resolved by name+namespace.

    Meant to be cached with a short TTL - used by name-based lookups
    (get_agent_yaml_from_bucket, workflow agent references) that don't
    otherwise go through the cached-by-id identity row.
    """
    return f'agent_current_version:{namespace}:{agent_name}'


def get_agents_list_cache_key(namespace: Optional[str] = None) -> str:
    """Get cache key for agents list"""
    if namespace:
        return f'agents_list:namespace:{namespace}'
    return 'agents_list:all'


def get_namespace_cache_key(namespace_name: str) -> str:
    """Get cache key for namespace by name"""
    return f'namespace:name:{namespace_name}'


def get_namespaces_list_cache_key() -> str:
    """Get cache key for namespaces list"""
    return 'namespaces:list'


def get_workflow_by_id_cache_key(workflow_id: UUID) -> str:
    """Get cache key for workflow metadata by ID"""
    return f'workflow:id:{workflow_id}'


def get_workflow_yaml_cache_key(
    namespace: str, workflow_name: str, version: int
) -> str:
    """Get cache key for a specific version of a workflow's YAML content"""
    return f'workflow_yaml:{namespace}:{workflow_name}:{version}'


def get_workflow_current_version_cache_key(namespace: str, workflow_name: str) -> str:
    """
    Get cache key for a workflow's current_version, resolved by name+namespace.

    Meant to be cached with a short TTL - used by name-based lookups
    (get_workflow_yaml_from_bucket, subworkflow references, v1 inference)
    that don't otherwise go through the cached-by-id identity row.
    """
    return f'workflow_current_version:{namespace}:{workflow_name}'


def get_workflows_list_cache_key(namespace: Optional[str] = None) -> str:
    """Get cache key for workflows list"""
    if namespace:
        return f'workflows_list:namespace:{namespace}'
    return 'workflows_list:all'
