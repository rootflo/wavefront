"""Service for the namespaced runtime configuration store.

Holds static reference data that deterministic workflow steps need at execution
time — thresholds, limits, lookup tables. The `value` is an
arbitrary JSON document that wavefront never interprets.
"""

import json
import re
from typing import Any, Dict, List, Optional

from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.agentic_configuration import AgenticConfiguration
from db_repo_module.models.namespace import Namespace
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from common_module.log.logger import logger

# Configs are static and read on every workflow run, so they cache well. Writes
# invalidate explicitly, making the TTL a backstop rather than the mechanism.
CONFIGURATION_CACHE_TTL_SECONDS = 60 * 60


# Keys are a URL path segment, so they are restricted to what addresses cleanly.
# Same rule as agents_module's validate_agent_workflow_name.
CONFIGURATION_KEY_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$')


def get_configuration_cache_key(namespace: str, key: str) -> str:
    return f'configuration:{namespace}:{key}'


class NamespaceNotFoundError(Exception):
    """The namespace a configuration was written to does not exist.

    Raised in preference to letting the foreign key fail, which would surface as
    an opaque IntegrityError and a 500. The caller almost always mistyped.
    """


class ConfigurationAlreadyExistsError(Exception):
    """A configuration with this (namespace, key) already exists."""


class InvalidConfigurationKeyError(Exception):
    """The configuration key cannot be addressed in a URL path.

    Keys are a path segment in /v1/configurations/{namespace}/{key}, and the
    ASGI server percent-decodes the path before routing — so a key containing
    '/' is unreachable even when the client encodes it as %2F. A POST would
    create the row and every subsequent GET/PUT/DELETE would 404 on it.

    The pattern matches validate_agent_workflow_name in agents_module, which
    restricts agent and workflow names for the same reason. It is duplicated
    rather than imported to avoid giving plugins_module a dependency on
    agents_module (see _assert_namespace_exists).
    """


class InvalidConfigurationValueError(Exception):
    """The configuration document is null.

    Refused on write for two reasons. A null document is meaningless — there is
    nothing for a workflow to read out of it. And it would be unreachable:
    `value` is jsonb NOT NULL, but SQLAlchemy maps Python None onto JSON `null`
    rather than SQL NULL (none_as_null is False by default), so the row stores
    successfully and then reads back as None — indistinguishable from "no such
    configuration". GET would answer 404 for a row DELETE could still find.

    Rejecting it here is what lets None mean exactly one thing on read.
    """


class ConfigurationService:
    def __init__(
        self,
        configuration_repository: SQLAlchemyRepository[AgenticConfiguration],
        namespace_repository: SQLAlchemyRepository[Namespace],
        cache_manager: CacheManager,
    ) -> None:
        self.configuration_repository = configuration_repository
        self.namespace_repository = namespace_repository
        self.cache_manager = cache_manager

    async def _assert_namespace_exists(self, namespace: str) -> None:
        # Deliberately not get-or-create, the way AgentCrudService does it:
        # namespace_service lives in agents_module, and importing it here would
        # give plugins_module a cross-module dependency it does not have.
        if not await self.namespace_repository.find_one(name=namespace):
            raise NamespaceNotFoundError(
                f"Namespace '{namespace}' does not exist. "
                'Create it first via POST /v1/namespaces.'
            )

    @staticmethod
    def _assert_key_addressable(key: str) -> None:
        if not CONFIGURATION_KEY_PATTERN.match(key or ''):
            raise InvalidConfigurationKeyError(
                f"Configuration key '{key}' is invalid. It must start with a "
                'letter or number and contain only letters, numbers, hyphens '
                'and underscores — the key is a URL path segment, so a key '
                "containing '/' could be created but never read back."
            )

    @staticmethod
    def _assert_value_not_null(value: Any) -> None:
        # Guarded in the service, not just the controller, so the invariant
        # holds for every caller — it is what makes `get_value` returning None
        # unambiguously mean "no such configuration".
        if value is None:
            raise InvalidConfigurationValueError(
                'Configuration value cannot be null. Store an object, array or '
                'scalar; use DELETE to remove a configuration.'
            )

    def _invalidate(self, namespace: str, key: str) -> None:
        try:
            self.cache_manager.remove(get_configuration_cache_key(namespace, key))
        except Exception as e:
            # A stale cache entry is recoverable (it expires); failing the write
            # after the row is committed is not.
            logger.warning(
                f'Failed to invalidate configuration cache for {namespace}/{key}: {e}'
            )

    async def get_value(self, namespace: str, key: str) -> Optional[Any]:
        """Return the config document, or None if there is no such key.

        None is unambiguous here only because writes refuse a null document —
        see InvalidConfigurationValueError. Every other falsy document (0, "",
        [], {}) is a real value and is returned as-is.

        This is the hot path — every workflow run that uses a config node hits it.
        """
        cache_key = get_configuration_cache_key(namespace, key)
        try:
            cached = self.cache_manager.get_str(cache_key)
            if cached is not None:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f'Configuration cache read failed for {cache_key}: {e}')

        configuration = await self.configuration_repository.find_one(
            namespace=namespace, key=key
        )
        if not configuration:
            return None

        try:
            self.cache_manager.add(
                cache_key,
                json.dumps(configuration.value),
                expiry=CONFIGURATION_CACHE_TTL_SECONDS,
            )
        except Exception as e:
            logger.warning(f'Configuration cache write failed for {cache_key}: {e}')

        return configuration.value

    async def create(
        self,
        namespace: str,
        key: str,
        value: Any,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._assert_key_addressable(key)
        self._assert_value_not_null(value)
        await self._assert_namespace_exists(namespace)

        if await self.configuration_repository.find_one(namespace=namespace, key=key):
            raise ConfigurationAlreadyExistsError(
                f"Configuration '{key}' already exists in namespace '{namespace}'. "
                'Use PUT to replace it.'
            )

        configuration = await self.configuration_repository.create(
            namespace=namespace, key=key, value=value, description=description
        )
        self._invalidate(namespace, key)
        return AgenticConfiguration.to_dict(configuration)

    async def upsert(
        self,
        namespace: str,
        key: str,
        value: Any,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._assert_key_addressable(key)
        self._assert_value_not_null(value)
        await self._assert_namespace_exists(namespace)

        # The repository's upsert returns None, so the row is read back to
        # report what was actually stored (including the server-set timestamps).
        await self.configuration_repository.upsert(
            filters={'namespace': namespace, 'key': key},
            value=value,
            description=description,
        )
        self._invalidate(namespace, key)

        configuration = await self.configuration_repository.find_one(
            namespace=namespace, key=key
        )
        return AgenticConfiguration.to_dict(configuration)

    async def delete(self, namespace: str, key: str) -> bool:
        existing = await self.configuration_repository.find_one(
            namespace=namespace, key=key
        )
        if not existing:
            return False

        await self.configuration_repository.delete_all(namespace=namespace, key=key)
        self._invalidate(namespace, key)
        return True

    async def list(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        """List configurations as metadata only.

        `value` is omitted: a document can be large, and a listing is for
        discovery, not for reading the documents.
        """
        filters = {'namespace': namespace} if namespace else {}
        configurations = await self.configuration_repository.find(**filters)
        return [
            {
                'id': str(configuration.id),
                'namespace': configuration.namespace,
                'key': configuration.key,
                'description': configuration.description,
                'created_at': configuration.created_at.isoformat(),
                'updated_at': configuration.updated_at.isoformat(),
            }
            for configuration in configurations
        ]
