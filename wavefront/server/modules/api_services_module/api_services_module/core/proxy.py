"""Core proxy functionality for handling API requests."""

from typing import Any, Dict, Optional, Union
from fastapi import HTTPException
from fastapi.responses import Response
from common_module.log.logger import logger
from ..models.pipeline import PipelineContext, PipelineException
from ..models.service import ProxyResponse, ServiceDefinition, ApiConfig
from ..config.registry import ServiceRegistry
from ..pipeline.builder import PipelineBuilder, PipelineCache
from ..auth.manager import AuthManager
from .manager import ApiServicesManager
from api_services_module.config.parser import ServiceDefinitionParser
from api_services_module.utils.api_change_publisher import (
    ApiChangePublisher,
    UpdateMessage,
)


class ApiProxy:
    """
    Core API proxy that orchestrates the entire request processing pipeline.

    Handles service routing, authentication, and request/response processing
    through the pipeline architecture.
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        api_services_manager: Optional[ApiServicesManager] = None,
        api_change_publisher: Optional[ApiChangePublisher] = None,
    ):
        self.service_registry = service_registry
        self.api_services_manager = api_services_manager
        self.api_change_publisher = api_change_publisher

        self.auth_manager = AuthManager()
        self.pipeline_cache = PipelineCache()
        self.pipeline_builder = PipelineBuilder()

        # Initialize auth manager with all registered services
        self._initialize_auth_manager()

    def _require_api_services_manager(self):
        if not self.api_services_manager:
            raise HTTPException(
                status_code=500,
                detail='API services manager is not configured for this proxy',
            )

    def _initialize_auth_manager(self):
        """Initialize auth manager with all registered services."""
        for service in self.service_registry.get_all_services().values():
            self.auth_manager.register_service_auth(service)

    async def process_request(
        self,
        service_id: str,
        api_id: str,
        api_version: str = 'v1',
        method: str = 'POST',
        path: str = '',
        path_params: Optional[Dict[str, str]] = None,
        query_params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Any] = None,
    ) -> Union[ProxyResponse, Response]:
        """
        Process an API request through the proxy pipeline.

        Args:
            service_id: Target service identifier
            api_id: Target API identifier
            api_version: API version (default: v1)
            method: HTTP method
            path: Request path
            path_params: Path parameters extracted from URL
            query_params: Query parameters
            headers: Request headers
            body: Request body

        Returns:
            Union[ProxyResponse, Response] with standardized format (JSON/text via ProxyResponse, binary via fastapi.Response)

        Raises:
            HTTPException: For various error conditions
        """
        # Create pipeline context
        context = PipelineContext(
            service_id=service_id,
            api_id=api_id,
            api_version=api_version,
            method=method,
            path=path,
            path_params=path_params or {},
            query_params=query_params or {},
            headers=headers or {},
            body=body,
        )

        context.add_trace(
            'proxy', f'Starting request processing for {service_id}/{api_id}'
        )

        try:
            # Get service definition
            service_definition = self.service_registry.get_service(service_id)
            if not service_definition:
                raise HTTPException(
                    status_code=404, detail=f'Service not found: {service_id}'
                )

            # Get API configuration
            api_config = service_definition.get_api_by_id(api_id, api_version)
            if not api_config:
                raise HTTPException(
                    status_code=404,
                    detail=f'API not found: {api_id} (version: {api_version}) in service: {service_id}',
                )

            context.add_trace('proxy', 'Found service and API configuration')

            # Get or build pipeline
            pipeline = self._get_or_build_pipeline(service_definition, api_config)

            # Execute pipeline
            context = await pipeline.execute(context)

            # Check if response is binary content
            if context.is_binary_response and context.raw_response_content is not None:
                # Return binary response directly with original headers. Remove content-type from headers to avoid duplication.
                context.add_trace('proxy', 'Returning binary response directly')
                # Copy headers and pop content-type for media_type
                _headers = dict(context.response_headers)
                _media_type = _headers.pop('content-type', None)
                return Response(
                    content=context.raw_response_content,
                    status_code=context.response_status,
                    headers=_headers,
                    media_type=_media_type,
                )

            # Create successful response for JSON/text content
            response = ProxyResponse.success(
                data=context.response_body,
                trace=context.execution_trace,
                message='Request processed successfully',
                http_status_code=context.response_status,
            )

            context.add_trace('proxy', 'Request processing completed successfully')
            return response

        except HTTPException as e:
            logger.error(f'HTTPException: {str(e)}', exc_info=True)
            raise

        except PipelineException as e:
            logger.error(f'PipelineException: {str(e)}', exc_info=True)
            context.add_trace('proxy', f'Pipeline error: {str(e)}')

            # Special handling for payload validation errors
            if 'payload_validator' in e.stage_name:
                return ProxyResponse.error(
                    message=e.message,
                    trace=context.execution_trace,
                    status='validation_error',
                    http_status_code=400,  # Bad Request for validation errors
                )

            # Default pipeline error handling
            return ProxyResponse.error(
                message=f'Pipeline error: {e.message}',
                trace=context.execution_trace,
                status='api_pipeline_error',
                http_status_code=502,  # Bad Gateway for pipeline errors
            )

        except Exception as e:
            logger.error(f'Exception: {str(e)}', exc_info=True)
            context.add_trace('proxy', f'Unexpected error: {str(e)}')
            return ProxyResponse.error(
                message='Internal error',
                trace=context.execution_trace,
                status='internal_error',
                http_status_code=500,
            )

    def _get_or_build_pipeline(
        self, service_definition: ServiceDefinition, api_config: ApiConfig
    ):
        """Get cached pipeline or build new one."""
        # Try to get from cache first
        pipeline = self.pipeline_cache.get_pipeline(
            service_definition.id, api_config.id, api_config.version
        )

        if pipeline is None:
            # Build new pipeline
            pipeline = self.pipeline_builder.build_service_pipeline(
                service_definition, api_config
            )

            # Cache the pipeline
            self.pipeline_cache.cache_pipeline(
                service_definition.id, api_config.id, pipeline, api_config.version
            )

        return pipeline

    async def reload_service(self, service_id: str):
        """
        Reload a service configuration.

        Args:
            service_id: Service to reload
        """
        try:
            # Reload service definition
            await self.service_registry.reload_service(service_id)

            # Re-register auth
            service_definition = self.service_registry.get_service(service_id)
            if service_definition:
                self.auth_manager.register_service_auth(service_definition)

            # Invalidate cached pipelines
            self.pipeline_cache.invalidate_service(service_id)

        except Exception as e:
            logger.error(f'Failed with error: {str(e)}', exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f'Failed to reload service {service_id}',
            )

    def remove_service(self, service_id: str):
        """
        Remove a service from in-memory state.

        This cleans up:
        - Service registry
        - Auth manager
        - Pipeline cache

        Args:
            service_id: Service to remove
        """
        logger.info(f'Removing service from in-memory state: {service_id}')

        # Remove from registry
        self.service_registry.deregister_service(service_id)
        logger.info(f'Removed service from registry: {service_id}')

        # Remove auth handler
        self.auth_manager.remove_service_auth(service_id)
        logger.info(f'Removed auth handler for service: {service_id}')

        # Invalidate cached pipelines
        self.pipeline_cache.invalidate_service(service_id)
        logger.info(f'Invalidated pipelines for service: {service_id}')

    def _serialize_payload_schema(self, payload_schema) -> Dict[str, Any]:
        """
        Serialize PayloadSchema object to dictionary.

        Args:
            payload_schema: PayloadSchema object

        Returns:
            Dictionary representation of the schema
        """
        return {
            'fields': [
                {
                    'name': field.name,
                    'type': field.type,
                    'required': field.required,
                    'description': field.description,
                }
                for field in payload_schema.fields
            ]
        }

    def get_service_info(self, service_id: str) -> Dict[str, Any]:
        """
        Get information about a service.

        Args:
            service_id: Service identifier

        Returns:
            Service information dictionary
        """
        service_definition = self.service_registry.get_service(service_id)
        if not service_definition:
            raise HTTPException(
                status_code=404, detail=f'Service not found: {service_id}'
            )

        return {
            'service_id': service_definition.id,
            'base_url': service_definition.base_url,
            'auth': service_definition.auth,
            'apis': [
                {
                    'id': api.id,
                    'version': api.version,
                    'path': api.path,
                    'method': api.method.value,
                    'backend_path': api.backend_path,
                    'description': api.description,
                    'additional_headers': api.additional_headers,
                    'backend_query_params': api.backend_query_params,
                    'output_mapper_enabled': api.output_mapper_enabled,
                    'output_mapper': api.output_mapper,
                    'payload_schema': self._serialize_payload_schema(api.payload_schema)
                    if api.payload_schema
                    else None,
                }
                for api in service_definition.apis
            ],
        }

    def get_all_services_info(self) -> Dict[str, Any]:
        """Get information about all registered services."""
        services = []
        for service_id in self.service_registry.get_service_ids():
            try:
                services.append(self.get_service_info(service_id))
            except HTTPException as e:
                logger.error(f'Service Exception: {str(e)}', exc_info=True)
                # Skip services that can't be loaded
                continue

        return {
            'services': services,
            'stats': self.service_registry.get_stats(),
            'cache_stats': self.pipeline_cache.get_stats(),
        }

    def health_check(self) -> Dict[str, Any]:
        """Perform health check of the proxy."""
        try:
            stats = self.service_registry.get_stats()
            cache_stats = self.pipeline_cache.get_stats()

            return {
                'status': 'healthy',
                'services_count': stats['total_services'],
                'apis_count': stats['total_apis'],
                'cached_pipelines': cache_stats['cached_pipelines'],
                'auth_types_supported': ['bearer', 'basic', 'api_key'],
            }
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}

    async def create_api_services(self, service_yaml: str):
        self._require_api_services_manager()
        service_def: ServiceDefinition = ServiceDefinitionParser.parse_yaml_string(
            service_yaml
        )
        service_id = service_def.id
        service = await self.api_services_manager.get_api_service(id=service_id)
        if service:
            await self.reload_service(service_id)
            raise HTTPException(
                status_code=400,
                detail=f'Service already exists: {service_id}, reloaded again',
            )
        await self.api_services_manager.create_api_service(
            id=service_id, service_def_yaml=service_yaml
        )
        await self.reload_service(service_id)
        self.api_change_publisher.publish_message(
            UpdateMessage(
                service_id=service_id,
                operation='create',
                metadata={},
            )
        )

    async def update_api_services(self, id: str, service_yaml: str):
        self._require_api_services_manager()
        service_def: ServiceDefinition = ServiceDefinitionParser.parse_yaml_string(
            service_yaml
        )
        service_id = service_def.id
        if id != service_id:
            raise HTTPException(
                status_code=400, detail=f'Service ids dont match: {service_id} vs {id}'
            )
        service = await self.api_services_manager.get_api_service(id=service_id)
        if not service:
            raise HTTPException(
                status_code=404, detail=f'Service not found: {service_id}'
            )
        await self.api_services_manager.update_api_service(
            id=service_id, service_def_yaml=service_yaml
        )
        await self.reload_service(service_id)
        self.api_change_publisher.publish_message(
            UpdateMessage(
                service_id=service_id,
                operation='update',
                metadata={},
            )
        )

    async def delete_api_services(self, id: str):
        self._require_api_services_manager()
        await self.api_services_manager.delete_api_service(id)
        # Clean up in-memory state
        self.remove_service(id)
        self.api_change_publisher.publish_message(
            UpdateMessage(
                service_id=id,
                operation='delete',
                metadata={},
            )
        )
