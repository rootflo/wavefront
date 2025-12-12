"""Authentication manager for orchestrating auth handlers."""

from typing import Dict, Optional
from ..models.service import ServiceDefinition
from ..models.pipeline import PipelineContext
from .handlers import AuthHandler, AuthHandlerFactory


class AuthManager:
    """
    Central authentication manager that orchestrates different auth handlers.

    Manages authentication for multiple services and caches auth handlers
    for performance.
    """

    def __init__(self):
        self._auth_handlers: Dict[str, AuthHandler] = {}

    def register_service_auth(self, service_definition: ServiceDefinition):
        """Register authentication handler for a service."""
        auth_key = f'{service_definition.id}:{service_definition.auth.version}'

        if auth_key not in self._auth_handlers:
            handler = AuthHandlerFactory.create_handler(service_definition.auth)
            self._auth_handlers[auth_key] = handler

    def get_auth_handler(
        self, service_id: str, auth_version: str = 'v1'
    ) -> Optional[AuthHandler]:
        """Get authentication handler for a service."""
        auth_key = f'{service_id}:{auth_version}'
        return self._auth_handlers.get(auth_key)

    def authenticate(self, context: PipelineContext) -> PipelineContext:
        """
        Authenticate a request using the appropriate handler.

        Args:
            context: Pipeline context containing service information

        Returns:
            Modified context with authentication headers

        Raises:
            PipelineException: If authentication fails
        """
        auth_handler = self.get_auth_handler(context.service_id)

        if not auth_handler:
            raise ValueError(f'No auth handler found for service: {context.service_id}')

        return auth_handler.execute(context)

    def clear_cache(self):
        """Clear all cached auth handlers."""
        self._auth_handlers.clear()

    def remove_service_auth(self, service_id: str, auth_version: str = 'v1'):
        """Remove auth handler for a specific service."""
        auth_key = f'{service_id}:{auth_version}'
        self._auth_handlers.pop(auth_key, None)
