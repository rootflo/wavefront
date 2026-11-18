"""
Utilities for parsing versioned agent/workflow references, e.g. "namespace/name@2",
and for resolving an entity's current_version by name+namespace.
"""

from typing import Any, Optional, Tuple


def parse_versioned_reference(
    name_with_optional_version: str,
) -> Tuple[str, Optional[int]]:
    """
    Split a reference's name segment into (name, version).

    "summarizer@2" -> ("summarizer", 2)
    "summarizer"   -> ("summarizer", None) - caller should resolve to current_version

    Args:
        name_with_optional_version: The name segment of a reference (i.e. the part
            after "namespace/"), optionally suffixed with "@<version>"

    Returns:
        Tuple[str, Optional[int]]: (name, version or None if unversioned)

    Raises:
        ValueError: If a "@" suffix is present but isn't a valid integer version
    """
    if '@' not in name_with_optional_version:
        return name_with_optional_version, None

    name, version_str = name_with_optional_version.rsplit('@', 1)
    try:
        return name, int(version_str)
    except ValueError:
        raise ValueError(
            f'Invalid version suffix in reference: {name_with_optional_version}'
        )


async def resolve_entity_current_version(
    *,
    cache_manager: Any,
    repository: Any,
    namespace: str,
    name: str,
    cache_key: str,
    ttl: int,
    not_found_message: str,
) -> int:
    """
    Resolve an agent/workflow's current_version by namespace+name, via a short-TTL
    cache so name-based lookups (no explicit version) don't hit the DB on every call.

    Shared by AgentCrudService, WorkflowCrudService and WorkflowInferenceService.
    Cache calls use the async client; a Redis failure falls back to the database.

    Args:
        cache_manager: CacheManager instance
        repository: SQLAlchemyRepository for the entity, exposing find_one(name=, namespace=)
        namespace: The namespace name
        name: The entity (agent/workflow) name
        cache_key: Pre-built cache key for the current-version cache entry
        ttl: Cache TTL in seconds
        not_found_message: ValueError message if no entity matches name+namespace

    Raises:
        ValueError: If no entity matches name+namespace
    """
    cached_version = await cache_manager.try_aget_str(cache_key)
    if cached_version:
        return int(cached_version)

    entity = await repository.find_one(name=name, namespace=namespace)
    if not entity:
        raise ValueError(not_found_message)

    await cache_manager.try_aadd(cache_key, str(entity.current_version), expiry=ttl)
    return entity.current_version
