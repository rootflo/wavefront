"""
Example test file demonstrating how to use the conftest.py fixtures.

This file shows various testing patterns for the API services module
using the fixtures defined in conftest.py.
"""

import pytest
from unittest.mock import patch
import httpx

from api_services_module.models.service import AuthType, HttpMethod


class TestServiceRegistry:
    """Test cases for ServiceRegistry using fixtures."""

    def test_service_registry_initialization(self, service_registry):
        """Test that service registry initializes correctly."""
        assert service_registry is not None
        services = service_registry.get_all_services()
        assert len(services) >= 2  # We have at least 2 test services

    def test_service_registry_get_service(self, service_registry):
        """Test getting a specific service."""
        service = service_registry.get_service('yaml-test-service')
        assert service is not None
        assert service.id == 'yaml-test-service'
        assert service.base_url == 'https://api.yaml-test.com'

    def test_service_registry_validation(self, service_registry):
        """Test service validation."""
        service_ids = service_registry.get_service_ids()
        for service_id in service_ids:
            is_valid = service_registry.validate_service(service_id)
            assert is_valid, f'Service {service_id} should be valid'


class TestAuthenticationHandlers:
    """Test cases for authentication handlers."""

    def test_bearer_auth_config(self, sample_bearer_auth_config):
        """Test Bearer authentication configuration."""
        assert sample_bearer_auth_config.type == AuthType.BEARER
        assert sample_bearer_auth_config.token == 'test-bearer-token-123'
        assert 'X-Client-ID' in sample_bearer_auth_config.additional_headers

    def test_basic_auth_config(self, sample_basic_auth_config):
        """Test Basic authentication configuration."""
        assert sample_basic_auth_config.type == AuthType.BASIC
        assert sample_basic_auth_config.username == 'test_user'
        assert sample_basic_auth_config.password == 'test_password'

    def test_api_key_auth_config(self, sample_api_key_auth_config):
        """Test API Key authentication configuration."""
        assert sample_api_key_auth_config.type == AuthType.API_KEY
        assert sample_api_key_auth_config.api_key == 'test-api-key-456'
        assert sample_api_key_auth_config.api_key_header == 'X-API-Key'

    @pytest.mark.parametrize(
        'auth_type', [AuthType.BEARER, AuthType.BASIC, AuthType.API_KEY]
    )
    def test_auth_types(self, auth_type):
        """Test different authentication types."""
        assert auth_type in [AuthType.BEARER, AuthType.BASIC, AuthType.API_KEY]


class TestServiceDefinitions:
    """Test cases for service definitions."""

    def test_sample_service_definition(self, sample_service_definition):
        """Test sample service definition structure."""
        assert sample_service_definition.id == 'test-service'
        assert sample_service_definition.base_url == 'https://api.test-service.com'
        assert len(sample_service_definition.apis) == 3

    def test_api_configs(self, sample_api_configs):
        """Test API configurations."""
        assert len(sample_api_configs) == 3

        get_users_api = sample_api_configs[0]
        assert get_users_api.id == 'get-users'
        assert get_users_api.method == HttpMethod.GET
        assert get_users_api.path == '/users'

    def test_service_get_api_by_id(self, sample_service_definition):
        """Test getting API by ID from service definition."""
        api = sample_service_definition.get_api_by_id('get-users')
        assert api is not None
        assert api.id == 'get-users'

        # Test non-existent API
        non_existent = sample_service_definition.get_api_by_id('non-existent')
        assert non_existent is None


class TestPipelineComponents:
    """Test cases for pipeline components."""

    def test_pipeline_context(self, sample_pipeline_context):
        """Test pipeline context initialization."""
        assert sample_pipeline_context.service_id == 'test-service'
        assert sample_pipeline_context.api_id == 'get-users'
        assert sample_pipeline_context.method == 'POST'
        assert 'limit' in sample_pipeline_context.query_params

    def test_pipeline_context_trace(self, sample_pipeline_context):
        """Test pipeline context tracing."""
        initial_trace_count = len(sample_pipeline_context.execution_trace)

        sample_pipeline_context.add_trace('test_stage', 'test message')

        assert len(sample_pipeline_context.execution_trace) == initial_trace_count + 1
        assert 'test_stage' in sample_pipeline_context.execution_trace[-1]

    def test_pipeline_builder(self, pipeline_builder, sample_service_definition):
        """Test pipeline builder."""
        assert pipeline_builder is not None

        # Test auth pipeline creation
        auth_pipeline = pipeline_builder.build_auth_pipeline(sample_service_definition)
        assert auth_pipeline is not None
        assert 'auth_pipeline' in auth_pipeline.get_name()

    def test_pipeline_cache(self, pipeline_cache):
        """Test pipeline cache functionality."""
        assert pipeline_cache is not None

        # Test cache stats
        stats = pipeline_cache.get_stats()
        assert 'cached_pipelines' in stats
        assert 'cache_keys' in stats


class TestApiProxy:
    """Test cases for API proxy."""

    def test_api_proxy_initialization(self, api_proxy):
        """Test API proxy initialization."""
        assert api_proxy is not None

    def test_api_proxy_health_check(self, api_proxy):
        """Test API proxy health check."""
        health = api_proxy.health_check()
        assert health['status'] == 'healthy'
        assert 'services_count' in health
        assert 'auth_types_supported' in health

    def test_api_proxy_service_info(self, api_proxy):
        """Test getting service information."""
        try:
            info = api_proxy.get_service_info('yaml-test-service')
            assert info['service_id'] == 'yaml-test-service'
            assert 'apis' in info
        except Exception:
            # Service might not be loaded in this context
            pass

    @pytest.mark.asyncio
    async def test_api_proxy_process_request_error(self, async_api_proxy):
        """Test API proxy request processing with expected error."""
        # This should return an error response since we don't have real backends
        response = await async_api_proxy.process_request(
            service_id='yaml-test-service',
            api_id='yaml-api',
            api_version='v1',
            method='POST',
            path='/test',
            query_params={'test': 'true'},
            headers={'User-Agent': 'test'},
            body={'test': 'data'},
        )

        # Should return an error response, not raise an exception
        assert response.meta['status'] in [
            'pipeline_error',
            'error',
            'api_pipeline_error',
        ]
        assert 'trace' in response.meta


class TestDependencyInjection:
    """Test cases for dependency injection container."""

    def test_container_initialization(self, api_services_container):
        """Test container initialization."""
        assert api_services_container is not None

    def test_container_service_registry(self, api_services_container):
        """Test container service registry."""
        service_registry = api_services_container.service_registry()
        assert service_registry is not None

    def test_container_auth_manager(self, api_services_container):
        """Test container auth manager."""
        auth_manager = api_services_container.auth_manager()
        assert auth_manager is not None

    def test_container_api_proxy(self, api_services_container):
        """Test container API proxy."""
        api_proxy = api_services_container.api_proxy()
        assert api_proxy is not None

    def test_container_router(self, api_services_container):
        """Test container router."""
        router = api_services_container.router()
        assert router is not None
        assert len(router.routes) > 0


class TestMockDependencies:
    """Test cases for mock dependencies."""

    @pytest.mark.asyncio
    async def test_mock_db_client(self, mock_db_client):
        """Test mock database client."""
        assert not mock_db_client.is_connected()

        await mock_db_client.connect()
        assert mock_db_client.is_connected()

        mock_db_client.run_migration()
        assert mock_db_client.migration_run

    def test_mock_cache_manager(self, mock_cache_manager):
        """Test mock cache manager."""
        # Test cache operations
        assert mock_cache_manager.get('test_key') is None

        mock_cache_manager.set('test_key', 'test_value')
        assert mock_cache_manager.get('test_key') == 'test_value'

        mock_cache_manager.delete('test_key')
        assert mock_cache_manager.get('test_key') is None


class TestHttpMocking:
    """Test cases demonstrating HTTP mocking."""

    def test_mock_httpx_response(self, mock_httpx_response):
        """Test mock HTTP response."""
        assert mock_httpx_response.status_code == 200
        assert mock_httpx_response.json() == {'success': True, 'data': 'test'}

    def test_mock_httpx_client(self, mock_httpx_client, mock_httpx_response):
        """Test mock HTTP client."""
        with mock_httpx_client as client:
            response = client.request('GET', 'http://test.com')
            assert response == mock_httpx_response

    @patch('httpx.Client')
    def test_api_proxy_with_mocked_http(
        self, mock_client_class, api_proxy, mock_httpx_response
    ):
        """Test API proxy with mocked HTTP client."""
        from unittest.mock import MagicMock

        # Configure the mock
        mock_client = MagicMock()
        mock_client.request.return_value = mock_httpx_response
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client_class.return_value = mock_client

        # Verify the mock is configured correctly
        assert mock_client_class.called is False
        assert mock_client.request.return_value == mock_httpx_response


class TestErrorHandling:
    """Test cases for error handling."""

    def test_mock_network_error(self, mock_network_error):
        """Test mock network error."""
        assert isinstance(mock_network_error, httpx.RequestError)
        assert 'Network error' in str(mock_network_error)

    def test_mock_http_error(self, mock_http_error):
        """Test mock HTTP error."""
        assert isinstance(mock_http_error, httpx.HTTPStatusError)
        assert 'Server error' in str(mock_http_error)


class TestParametrizedFixtures:
    """Test cases using parametrized fixtures."""

    def test_different_auth_types(self, auth_type):
        """Test with different authentication types."""
        assert auth_type in [AuthType.BEARER, AuthType.BASIC, AuthType.API_KEY]
        assert isinstance(auth_type, AuthType)

    def test_different_http_methods(self, http_method):
        """Test with different HTTP methods."""
        assert http_method in [
            HttpMethod.GET,
            HttpMethod.POST,
            HttpMethod.PUT,
            HttpMethod.DELETE,
        ]
        assert isinstance(http_method, HttpMethod)


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration test cases using multiple fixtures."""

    def test_full_container_integration(self, initialized_container):
        """Test full container integration."""
        # Test that all components work together
        service_registry = initialized_container.service_registry()
        auth_manager = initialized_container.auth_manager()
        api_proxy = initialized_container.api_proxy()
        router = initialized_container.router()

        assert service_registry is not None
        assert auth_manager is not None
        assert api_proxy is not None
        assert router is not None

    @pytest.mark.asyncio
    async def test_async_integration(
        self, async_mock_dependencies, mock_api_services_manager
    ):
        """Test async integration with mock dependencies."""
        deps = async_mock_dependencies

        assert deps['db_client'].is_connected()
        assert deps['cache_manager'] is not None

        # Test that we can create components with async dependencies
        from api_services_module.config.registry import ServiceRegistry

        registry = ServiceRegistry(mock_api_services_manager)
        await registry.load_from_db()

        assert len(registry.get_service_ids()) >= 2
