"""Service registry for managing service definitions."""

from typing import Dict, List, Optional
from ..models.service import ServiceDefinition
from .parser import ServiceDefinitionParser
from common_module.log.logger import logger
from ..core.manager import ApiServicesManager


class ServiceRegistry:
    """
    Registry for managing service definitions.

    Provides CRUD operations for service definitions and handles
    loading from YAML files.
    """

    def __init__(self, api_service_manager: Optional[ApiServicesManager] = None):
        """
        Initialize service registry.

        Args:
            config_directory: Directory containing service definition files
        """
        self.api_service_manager = api_service_manager

        self._services: Dict[str, ServiceDefinition] = {}
        self.parser = ServiceDefinitionParser()

    def register_service(self, service_definition: ServiceDefinition):
        """
        Register a service definition.

        Args:
            service_definition: Service definition to register
        """
        self._services[service_definition.id] = service_definition

    def deregister_service(self, service_id: str):
        """
        Register a service definition.

        Args:
            service_definition: Service definition to register
        """
        self._services.pop(service_id, None)
        logger.info(f'Service removed from runtime: {service_id}')

    def get_service(self, service_id: str) -> Optional[ServiceDefinition]:
        """
        Get a service definition by ID.

        Args:
            service_id: Service identifier

        Returns:
            ServiceDefinition if found, None otherwise
        """
        return self._services.get(service_id)

    def get_all_services(self) -> Dict[str, ServiceDefinition]:
        """Get all registered service definitions."""
        return self._services.copy()

    def get_service_ids(self) -> List[str]:
        """Get list of all registered service IDs."""
        return list(self._services.keys())

    def remove_service(self, service_id: str) -> bool:
        """
        Remove a service definition.

        Args:
            service_id: Service identifier

        Returns:
            True if service was removed, False if not found
        """
        if service_id in self._services:
            del self._services[service_id]
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
            self.register_service(service_definition)

        logger.info(f'Loaded {len(self._services)} service definitions from db')

    async def load_service_from_db(self, service_id: str):
        self._ensure_manager()

        service = await self.api_service_manager.get_api_service(id=service_id)
        if not service:
            raise ValueError(f'No service definition found for service: {service_id}')
        service_def_yaml = self.api_service_manager.fetch_service_def(service)
        service_def = self.parser.parse_yaml_string(service_def_yaml)
        self.register_service(service_definition=service_def)

        logger.info(f'Loaded service from db: {service_id}')

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
