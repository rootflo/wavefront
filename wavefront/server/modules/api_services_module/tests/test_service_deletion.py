import sys

# Add paths to sys.path
import os
import asyncio
import logging
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from common_module.response_formatter import ResponseFormatter
from api_services_module.core.router import ProxyRouter
from api_services_module.core.proxy import ApiProxy
from api_services_module.config.registry import ServiceRegistry
from api_services_module.models.service import (
    ServiceDefinition,
    AuthConfig,
    ApiConfig,
    AuthType,
    HttpMethod,
)


# Mock redis module before imports
def create_module_mock():
    """Create a MagicMock configured to support nested module imports."""
    mock = MagicMock()
    mock.__path__ = []  # Required for nested package imports
    return mock


sys.modules['redis'] = MagicMock()
sys.modules['flo_cloud'] = create_module_mock()
sys.modules['flo_cloud.gcp'] = create_module_mock()
sys.modules['flo_cloud.gcp.bigquery'] = create_module_mock()
sys.modules['flo_cloud.cloud_storage'] = create_module_mock()

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), '../../common_module'))
)
sys.path.append(
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), '../../api_services_module')
    )
)
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), '../../db_repo_module'))
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_service_deletion_cleanup():
    logger.info('Starting test_service_deletion_cleanup')

    # Setup
    api_services_manager = AsyncMock()
    service_registry = ServiceRegistry(api_services_manager)
    response_formatter = ResponseFormatter()

    # Create a dummy service definition
    service_def = ServiceDefinition(
        id='test-service',
        base_url='http://test.com',
        auth=AuthConfig(id='test-auth', type=AuthType.BEARER, token='token'),
        apis=[
            ApiConfig(
                id='test-api', path='/test', backend_path='/test', method=HttpMethod.GET
            )
        ],
    )

    # Register service manually
    service_registry.register_service(service_def)

    api_change_publisher = AsyncMock()
    api_proxy = ApiProxy(service_registry, api_services_manager, api_change_publisher)

    # Initialize Proxy and Router
    proxy_router = ProxyRouter(
        api_proxy, service_registry, response_formatter, api_services_manager
    )
    app = FastAPI()
    proxy_router.set_app(app)

    # Force route setup
    proxy_router._setup_dynamic_api_routes()

    # Verify initial state
    logger.info('Verifying initial state...')
    assert (
        service_registry.get_service('test-service') is not None
    ), 'Service not in registry'
    # Initialize auth manager manually since we didn't go through full init flow
    proxy_router.proxy._initialize_auth_manager()
    assert (
        proxy_router.proxy.auth_manager.get_auth_handler('test-service') is not None
    ), 'Auth handler not found'

    # Cache a pipeline
    pipeline = proxy_router.proxy._get_or_build_pipeline(
        service_def, service_def.apis[0]
    )
    assert (
        proxy_router.proxy.pipeline_cache.get_pipeline('test-service', 'test-api')
        is not None
    ), 'Pipeline not cached'

    # Verify routes exist
    route_names = [r.name for r in proxy_router.router.routes]
    assert 'proxy_test-service_test-api_v1' in route_names, 'Route not found in router'

    app_route_names = [r.name for r in app.router.routes]
    assert (
        'proxy_test-service_test-api_v1_app' in app_route_names
    ), 'Route not found in app'

    logger.info('Initial state verified.')

    # --- ACTION: Delete Service ---
    logger.info('Deleting service...')
    await proxy_router.proxy.delete_api_services('test-service')
    # Also remove routes (this is what the endpoint does)
    proxy_router.remove_service_routes('test-service')

    # --- VERIFICATION ---
    logger.info('Verifying cleanup...')

    failures = []

    # 1. Registry
    service = service_registry.get_service('test-service')
    if service:
        failures.append('FAIL: Service still in registry')
    else:
        logger.info('PASS: Service removed from registry')

    # 2. Auth Manager
    auth = proxy_router.proxy.auth_manager.get_auth_handler('test-service')
    if auth:
        failures.append('FAIL: Auth handler still exists')
    else:
        logger.info('PASS: Auth handler removed')

    # 3. Pipeline Cache
    pipeline = proxy_router.proxy.pipeline_cache.get_pipeline(
        'test-service', 'test-api'
    )
    if pipeline:
        failures.append('FAIL: Pipeline still cached')
    else:
        logger.info('PASS: Pipeline invalidated')

    # 4. Routes
    route_names = [r.name for r in proxy_router.router.routes]
    if 'proxy_test-service_test-api_v1' in route_names:
        failures.append('FAIL: Route still exists in router')
    else:
        logger.info('PASS: Route removed from router')

    app_route_names = [r.name for r in app.router.routes]
    if 'proxy_test-service_test-api_v1_app' in app_route_names:
        failures.append('FAIL: Route still exists in app')
    else:
        logger.info('PASS: Route removed from app')

    if failures:
        logger.error('\n'.join(failures))
        sys.exit(1)
    else:
        logger.info('All checks passed!')


if __name__ == '__main__':
    asyncio.run(test_service_deletion_cleanup())
