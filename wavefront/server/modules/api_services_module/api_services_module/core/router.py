"""FastAPI router for handling proxy requests."""

from fastapi import APIRouter, Request, HTTPException, Response
import json
from typing import Dict, List, Optional

from .proxy import ApiProxy
from .manager import ApiServicesManager
from ..config.registry import ServiceRegistry
from ..config.parser import ServiceDefinitionParser
from fastapi.responses import JSONResponse
from fastapi import status

from common_module.response_formatter import ResponseFormatter
from common_module.log.logger import logger


class ProxyRouter:
    """FastAPI router for handling API proxy requests with dynamic path support."""

    def __init__(
        self,
        proxy: ApiProxy,
        service_registry: ServiceRegistry,
        response_formatter: ResponseFormatter,
        api_services_manager: Optional[ApiServicesManager] = None,
    ):
        self.proxy = proxy
        self.service_registry = service_registry
        self.api_services_manager = api_services_manager
        self.response_formatter = response_formatter

        self.router = APIRouter()
        self.app: Optional[object] = None  # FastAPI app instance
        self.app_prefix: str = '/floware'  # Prefix used when including router in app
        self._setup_routes()

    def set_app(self, app, prefix: str = '/floware'):
        """Set the FastAPI app instance and prefix for dynamic route registration."""
        self.app = app
        self.app_prefix = prefix

    def _setup_routes(self):
        """Setup all proxy routes including dynamic routes based on service definitions."""
        # Setup static management routes first
        self._setup_management_routes()

        # Setup dynamic API routes based on service definitions
        # Only set up if services are available (skip if registry is empty)
        if self.service_registry.get_all_services():
            self._setup_dynamic_api_routes()
        else:
            logger.info(
                'Service registry is empty, skipping initial dynamic route setup. Routes will be loaded after services are loaded from database.'
            )

    def _setup_management_routes(self):
        """Setup service management and health check routes."""

        # Service management endpoints
        @self.router.get('/v1/api-services/{service_id}')
        async def get_service_info(service_id: str):
            """Get information about a specific service."""
            service = self.proxy.get_service_info(service_id)
            return self.response_formatter.buildSuccessResponse(service)

        @self.router.get('/v1/api-services')
        async def get_all_services():
            """Get information about all registered services."""
            services = self.proxy.get_all_services_info()
            return self.response_formatter.buildSuccessResponse(services)

        @self.router.post('/v1/api-services/{service_id}/reload')
        async def reload_service(service_id: str):
            """Reload a service configuration."""
            await self.proxy.reload_service(service_id)

            # Ensure dynamic routes match the reloaded service definition
            self.reload_service_routes(service_id)
            return {'message': f'Service {service_id} reloaded successfully'}

        # Authentication endpoint (for direct auth API calls)
        @self.router.post(
            '/v1/api-services/{service_id}/authenticators/{auth_version}/{auth_id}'
        )
        async def authenticate_direct(
            service_id: str, auth_version: str, auth_id: str, request: Request
        ):
            """
            Direct authentication endpoint.

            Allows clients to call authentication APIs directly if needed.
            """
            # This would be implemented if direct auth calls are needed
            # For now, return not implemented
            raise HTTPException(
                status_code=501,
                detail='Direct authentication calls not implemented in Phase 1',
            )

        @self.router.post('/v1/api-services')
        async def create_api_services(request: Request):
            yaml_content = (await request.body()).decode('utf-8')
            # Parse to get service_id before creating
            service_def = ServiceDefinitionParser.parse_yaml_string(yaml_content)
            service_id = service_def.id

            await self.proxy.create_api_services(yaml_content)
            # Reload routes for the newly created service
            self.reload_service_routes(service_id)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=self.response_formatter.buildSuccessResponse(
                    {'message': 'API Service created'}
                ),
            )

        @self.router.put('/v1/api-services/{id}')
        async def update_api_services(request: Request, id: str):
            yaml_content = (await request.body()).decode('utf-8')
            await self.proxy.update_api_services(id, yaml_content)
            # Reload routes for the updated service
            self.reload_service_routes(id)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=self.response_formatter.buildSuccessResponse(
                    {'message': 'API Service updated'}
                ),
            )

        @self.router.delete('/v1/api-services/{id}')
        async def delete_api_services(request: Request, id: str):
            await self.proxy.delete_api_services(id)
            # Remove routes for the deleted service
            self.remove_service_routes(id)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=self.response_formatter.buildSuccessResponse(
                    {'message': 'API Service deleted'}
                ),
            )

    def _setup_dynamic_api_routes(self):
        """Setup dynamic API routes based on service definitions."""
        # Get all services and their APIs
        route_configs = self._build_route_configurations()
        logger.info(
            f'Built {len(route_configs)} route configurations from service registry'
        )

        # Sort routes by specificity (more specific routes first)
        sorted_routes = self._sort_routes_by_specificity(route_configs)

        # Register routes in order
        registered_count = 0
        for route_config in sorted_routes:
            self._register_dynamic_route(route_config)
            registered_count += 1
        logger.info(f'Registered {registered_count} dynamic API routes')

    def _build_route_configurations(self) -> List[Dict]:
        """Build route configurations from all service definitions."""
        route_configs = []

        for service in self.service_registry.get_all_services().values():
            for api in service.apis:
                if api.path:
                    base = f'/v1/api-services/{service.id}/apis/{api.version}'
                    exposed_path = self._convert_path_to_fastapi_pattern(api.path)
                    # Ensure proper path concatenation (handle leading/trailing slashes)
                    if exposed_path.startswith('/'):
                        route_pattern = base + exposed_path
                    else:
                        route_pattern = base + '/' + exposed_path
                else:
                    raise ValueError(f'API {api.id} has no path')

                route_configs.append(
                    {
                        'pattern': route_pattern,
                        'service_id': service.id,
                        'api_id': api.id,
                        'api_version': api.version,
                        'api_path': api.path,
                        'api_method': api.method,
                        'specificity_score': self._calculate_specificity_score(
                            route_pattern
                        ),
                    }
                )

        return route_configs

    def _convert_path_to_fastapi_pattern(self, api_path: str) -> str:
        """
        Convert API path pattern to FastAPI route pattern.

        Example: /users/{id}/orders -> /users/{id}/orders
        FastAPI will handle the path parameter extraction.
        """
        return api_path

    def _calculate_specificity_score(self, route_pattern: str) -> int:
        """
        Calculate specificity score for route ordering.
        Higher score = more specific = should be registered first.

        Rules:
        - Static segments get higher score than parameterized segments
        - Longer paths get higher scores
        - Paths with fewer parameters get higher scores
        - More specific paths should come before less specific ones
        """
        segments = route_pattern.split('/')
        score = 0
        param_count = 0
        static_count = 0

        for segment in segments:
            if segment:  # Skip empty segments
                if '{' in segment and '}' in segment:
                    # Parameterized segment - lower value
                    score += 1
                    param_count += 1
                else:
                    # Static segment - higher value
                    score += 10
                    static_count += 1

        # Add bonus for path length (more segments = more specific)
        total_segments = len([s for s in segments if s])
        score += total_segments * 2

        # Penalty for parameters (fewer parameters = more specific)
        score -= param_count * 5

        # Bonus for static segments after the base API path
        # The base path is /v1/services/{service_id}/apis/{api_version}/{api_id}
        # So we look at segments after index 5 (0-based)
        api_segments = segments[6:] if len(segments) > 6 else []
        api_static_segments = sum(
            1 for seg in api_segments if seg and not ('{' in seg and '}' in seg)
        )
        score += api_static_segments * 20  # High bonus for API-level static segments

        return score

    def _sort_routes_by_specificity(self, route_configs: List[Dict]) -> List[Dict]:
        """Sort routes by specificity score (highest first)."""
        return sorted(route_configs, key=lambda x: x['specificity_score'], reverse=True)

    def _register_dynamic_route(self, route_config: Dict):
        """Register a dynamic route with FastAPI."""
        pattern = route_config['pattern']
        service_id = route_config['service_id']
        api_id = route_config['api_id']
        api_version = route_config['api_version']

        # Create the route handler
        async def dynamic_proxy_handler(request: Request, response: Response):
            """Dynamic proxy handler for API requests."""
            logger.info(
                f'Route handler called for pattern={pattern}, request_path={request.url.path}, method={request.method}'
            )
            try:
                # Extract path parameters from the request
                path_params = self._extract_path_parameters(request.url.path, pattern)
                logger.info(
                    f'Extracted path_params={path_params} for service={service_id}, api={api_id}'
                )

                # Extract request data
                headers = dict(request.headers)
                query_params = dict(request.query_params)

                # Get request body
                body = None
                if request.headers.get('content-type', '').startswith(
                    'application/json'
                ):
                    try:
                        body = await request.json()
                    except json.JSONDecodeError:
                        body = await request.body()
                else:
                    body_bytes = await request.body()
                    if body_bytes:
                        body = body_bytes

                trace = False
                if query_params:
                    trace = query_params.get('trace', '0') == '1'

                # Process request through proxy
                # Client always uses POST, but backend will use api_method from config
                proxy_response = await self.proxy.process_request(
                    service_id=service_id,
                    api_id=api_id,
                    api_version=api_version,
                    method='POST',  # Client always uses POST
                    path=request.url.path,
                    path_params=path_params,
                    query_params=query_params,
                    headers=headers,
                    body=body,
                    trace=trace,
                )

                # Set response status code
                response.status_code = proxy_response.http_status_code

                return proxy_response

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f'Failed to process request: {str(e)}', exc_info=True)
                raise HTTPException(status_code=500, detail=str(e))

        # Register the route with FastAPI
        # Clients always use POST to the proxy, backend uses api_method from config
        logger.info(
            f'Registering route: {pattern} for service={service_id}, api={api_id}, method=POST'
        )
        try:
            # Add to sub-router (for initial setup)
            self.router.add_api_route(
                pattern,
                dynamic_proxy_handler,
                methods=['POST'],
                name=f'proxy_{service_id}_{api_id}_{api_version}',
            )

            # Also add directly to app router if app is set (for dynamic route addition)
            if self.app is not None:
                full_pattern = self.app_prefix + pattern
                self.app.router.add_api_route(
                    full_pattern,
                    dynamic_proxy_handler,
                    methods=['POST'],
                    name=f'proxy_{service_id}_{api_id}_{api_version}_app',
                )
                logger.info(f'Also registered route in app router: {full_pattern}')

            logger.info(f'Successfully registered route: {pattern}')
        except Exception as e:
            logger.error(f'Failed to register route {pattern}: {str(e)}', exc_info=True)
            raise

    def _extract_path_parameters(
        self, request_path: str, route_pattern: str
    ) -> Dict[str, str]:
        """
        Extract path parameters from the request path.

        Args:
            request_path: The actual request path (includes /floware prefix)
            route_pattern: The FastAPI route pattern (without /floware prefix)

        Returns:
            Dictionary of parameter names and values
        """
        path_params = {}

        # Remove the /floware prefix from request path to match route pattern
        if request_path.startswith('/floware'):
            adjusted_request_path = request_path[8:]  # Remove '/floware'
        else:
            adjusted_request_path = request_path

        route_parts = route_pattern.split('/')
        request_parts = adjusted_request_path.split('/')

        # Match each part of the route pattern with the request
        for i, (route_part, request_part) in enumerate(zip(route_parts, request_parts)):
            if route_part.startswith('{') and route_part.endswith('}'):
                param_name = route_part[1:-1]  # Remove { and }
                path_params[param_name] = request_part

        return path_params

    def get_router(self) -> APIRouter:
        """Get the configured FastAPI router."""
        return self.router

    def reload_routes(self):
        """Reload dynamic routes after services are loaded into registry."""
        # Clear existing dynamic routes (keep management routes)
        # We'll rebuild all routes to include newly loaded services
        # Note: This doesn't remove routes, but adds new ones
        # FastAPI will handle duplicate route registration
        self._setup_dynamic_api_routes()

    def reload_service_routes(self, service_id: str):
        """Reload routes for a specific service after it's been created/updated."""
        service = self.service_registry.get_service(service_id)
        if not service:
            logger.warning(
                f'Service {service_id} not found in registry, skipping route registration'
            )
            return

        logger.info(f'Reloading routes for service: {service_id}')

        # Remove old routes first to prevent duplicates when routes are updated
        self.remove_service_routes(service_id)

        route_configs = []

        for api in service.apis:
            if api.path:
                base = f'/v1/api-services/{service.id}/apis/{api.version}'
                exposed_path = self._convert_path_to_fastapi_pattern(api.path)
                if exposed_path.startswith('/'):
                    route_pattern = base + exposed_path
                else:
                    route_pattern = base + '/' + exposed_path
            else:
                raise ValueError(f'API {api.id} has no path')

            route_configs.append(
                {
                    'pattern': route_pattern,
                    'service_id': service.id,
                    'api_id': api.id,
                    'api_version': api.version,
                    'api_path': api.path,
                    'api_method': api.method,
                    'specificity_score': self._calculate_specificity_score(
                        route_pattern
                    ),
                }
            )

        # Sort and register routes
        sorted_routes = self._sort_routes_by_specificity(route_configs)
        for route_config in sorted_routes:
            self._register_dynamic_route(route_config)

        logger.info(f'Registered {len(sorted_routes)} routes for service: {service_id}')

    def remove_service_routes(self, service_id: str):
        """Remove all routes for a specific service after it's been deleted."""
        logger.info(f'Removing routes for service: {service_id}')

        # Pattern to match route names for this service
        # Routes are named like: proxy_{service_id}_{api_id}_{api_version}
        route_name_prefix = f'proxy_{service_id}_'

        # Remove from sub-router
        original_count = len(self.router.routes)
        self.router.routes = [
            route
            for route in self.router.routes
            if not (
                hasattr(route, 'name')
                and route.name
                and route.name.startswith(route_name_prefix)
            )
        ]
        sub_router_removed = original_count - len(self.router.routes)
        logger.info(
            f'Removed {sub_router_removed} routes from sub-router for service: {service_id}'
        )

        # Remove from app router if app is set
        if self.app is not None:
            original_app_count = len(self.app.router.routes)
            self.app.router.routes = [
                route
                for route in self.app.router.routes
                if not (
                    hasattr(route, 'name')
                    and route.name
                    and route.name.startswith(route_name_prefix)
                )
            ]
            app_removed = original_app_count - len(self.app.router.routes)
            logger.info(
                f'Removed {app_removed} routes from app router for service: {service_id}'
            )

        logger.info(f'Completed route removal for service: {service_id}')
