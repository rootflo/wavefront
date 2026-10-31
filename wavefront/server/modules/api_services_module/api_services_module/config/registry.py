"""Service registry for managing service definitions."""

from typing import TYPE_CHECKING, Dict, List, Optional, Set
from ..models.service import ServiceDefinition
from .parser import ServiceDefinitionParser
from common_module.log.logger import logger
from ..core.manager import ApiServicesManager
from ..secrets.references import find_definition_refs, substitute_definition

if TYPE_CHECKING:
    from ..secrets.secret_store_service import SecretStoreService


class ServiceRegistry:
    """
    Registry for managing service definitions.

    Provides CRUD operations for service definitions and handles
    loading from YAML files.

    Each service is held twice: the definition as written, whose
    `${secrets.NAME}` references read paths show, and an execution copy with
    the references resolved, which auth and the pipelines use. The execution
    copy only lives in memory.
    """

    def __init__(
        self,
        api_service_manager: Optional[ApiServicesManager] = None,
        secret_store: Optional['SecretStoreService'] = None,
    ):
        """
        Initialize service registry.

        Args:
            api_service_manager: Source of the stored service definitions
            secret_store: Resolves `${secrets.NAME}` references
        """
        self.api_service_manager = api_service_manager
        self.secret_store = secret_store

        # Execution copies, references resolved
        self._services: Dict[str, ServiceDefinition] = {}
        # Definitions as stored, references kept
        self._definitions: Dict[str, ServiceDefinition] = {}
        # secret name -> ids of the services that reference it
        self._secret_refs: Dict[str, Set[str]] = {}
        self.parser = ServiceDefinitionParser()

    def register_service(
        self,
        service_definition: ServiceDefinition,
        execution_definition: Optional[ServiceDefinition] = None,
    ):
        """
        Register a service definition.

        Args:
            service_definition: Service definition as stored
            execution_definition: Copy with secrets resolved, if it differs
        """
        service_id = service_definition.id
        self._definitions[service_id] = service_definition
        self._services[service_id] = execution_definition or service_definition
        self._index_refs(service_id, find_definition_refs(service_definition))

    def deregister_service(self, service_id: str):
        """
        Register a service definition.

        Args:
            service_definition: Service definition to register
        """
        self._services.pop(service_id, None)
        self._definitions.pop(service_id, None)
        self._index_refs(service_id, set())
        logger.info(f'Service removed from runtime: {service_id}')

    def get_service(self, service_id: str) -> Optional[ServiceDefinition]:
        """
        Get the execution copy of a service, secrets resolved.

        Args:
            service_id: Service identifier

        Returns:
            ServiceDefinition if found, None otherwise
        """
        return self._services.get(service_id)

    def get_service_definition(self, service_id: str) -> Optional[ServiceDefinition]:
        """The service as stored, with `${secrets.NAME}` references unresolved."""
        return self._definitions.get(service_id)

    def services_referencing(self, secret_name: str) -> List[str]:
        """Ids of the registered services that reference `secret_name`, sorted."""
        return sorted(self._secret_refs.get(secret_name, ()))

    def get_all_services(self) -> Dict[str, ServiceDefinition]:
        """Get all registered service definitions."""
        return self._services.copy()

    def get_service_ids(self) -> List[str]:
        """Get list of all registered service IDs."""
        return list(self._services.keys())

    def get_definition_ids(self) -> List[str]:
        """Ids of every loaded definition, including services that failed to resolve."""
        return list(self._definitions.keys())

    def remove_service(self, service_id: str) -> bool:
        """
        Remove a service definition.

        Args:
            service_id: Service identifier

        Returns:
            True if service was removed, False if not found
        """
        if service_id in self._services:
            self.deregister_service(service_id)
            return True
        return False

    def _ensure_manager(self):
        if not self.api_service_manager:
            raise RuntimeError('API services manager is not configured')

    async def load_from_db(self):
        self._ensure_manager()

        services = await self.api_service_manager.get_all_api_services() or []
        self.clear_all()

        for service in services:
            yaml_content = self.api_service_manager.fetch_service_def(service)
            service_definition = self.parser.parse_yaml_string(yaml_content)
            try:
                execution_definition = await self.resolve_secrets(service_definition)
            except Exception as e:
                # One service with a bad reference must not keep the others from
                # loading. It gets no execution copy, so it serves no requests, but
                # it stays indexed so its secrets cannot be deleted from under it.
                # Read paths still list it, so it can be fixed from the console.
                self._definitions[service_definition.id] = service_definition
                self._index_refs(
                    service_definition.id, find_definition_refs(service_definition)
                )
                logger.error(
                    f'Skipping service {service_definition.id}: failed to resolve its secrets: {e}'
                )
                continue
            self.register_service(service_definition, execution_definition)

        logger.info(f'Loaded {len(self._services)} service definitions from db')

    async def load_service_from_db(self, service_id: str):
        self._ensure_manager()

        service = await self.api_service_manager.get_api_service(id=service_id)
        if not service:
            raise ValueError(f'No service definition found for service: {service_id}')
        service_def_yaml = self.api_service_manager.fetch_service_def(service)
        service_def = self.parser.parse_yaml_string(service_def_yaml)
        execution_def = await self.resolve_secrets(service_def)
        self.register_service(service_def, execution_def)

        logger.info(f'Loaded service from db: {service_id}')

    async def resolve_secrets(
        self, service_definition: ServiceDefinition
    ) -> ServiceDefinition:
        """Execution copy of a service with its `${secrets.NAME}` references resolved."""
        names = find_definition_refs(service_definition)
        if not names:
            return service_definition
        if not self.secret_store:
            raise RuntimeError('Secret store is not configured')
        resolved = await self.secret_store.resolve(names)
        return substitute_definition(service_definition, resolved)

    def _index_refs(self, service_id: str, names: Set[str]):
        """Make `names` the secrets `service_id` is indexed under."""
        for name in list(self._secret_refs):
            if name not in names:
                ids = self._secret_refs[name]
                ids.discard(service_id)
                if not ids:
                    del self._secret_refs[name]
        for name in names:
            self._secret_refs.setdefault(name, set()).add(service_id)

    async def reload_service(self, service_id: str):
        """
        Reload a specific service definition.

        Args:
            service_id: Service to reload
            file_path: Optional specific file path, otherwise searches config directory
        """
        self._ensure_manager()
        await self.load_service_from_db(service_id)

    def validate_service(self, service_id: str) -> bool:
        """
        Validate that a service definition is complete and valid.

        Args:
            service_id: Service to validate

        Returns:
            True if valid, False otherwise
        """
        service = self.get_service(service_id)
        if not service:
            return False

        # Basic validation
        if not service.id or not service.base_url:
            return False

        if not service.auth or not service.auth.type:
            return False

        # Validate at least one API is defined
        if not service.apis:
            return False

        # Validate each API
        for api in service.apis:
            if not api.id or not api.path or not api.method:
                return False

        return True

    def clear_all(self):
        """Clear all registered services."""
        self._services.clear()
        self._definitions.clear()
        self._secret_refs.clear()

    def get_stats(self) -> Dict[str, int]:
        """Get registry statistics."""
        total_apis = sum(len(service.apis) for service in self._services.values())

        return {
            'total_services': len(self._services),
            'total_apis': total_apis,
            'auth_types': len(
                set(service.auth.type for service in self._services.values())
            ),
        }
