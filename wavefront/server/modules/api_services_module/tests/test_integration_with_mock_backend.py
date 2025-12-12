"""
Integration tests with mock backend services for API Services Module.

This test file demonstrates full end-to-end testing of the API proxy
with mock backend services that simulate real API responses.
"""

import pytest
import asyncio
import json
from unittest.mock import patch, Mock, AsyncMock, MagicMock
from typing import Dict, Any

from api_services_module.models.service import AuthType, HttpMethod


class MockBackendService:
    """Mock backend service that simulates real API responses."""

    def __init__(self, base_url: str = 'https://api.mock-service.com'):
        self.base_url = base_url
        self.request_log = []
        self.responses = {}
        self.default_response = {
            'status': 'success',
            'data': {'message': 'Mock response'},
            'timestamp': '2024-01-01T00:00:00Z',
        }

    def set_response(
        self, path: str, method: str, response: Dict[str, Any], status_code: int = 200
    ):
        """Set a specific response for a path and method."""
        key = f'{method.upper()}:{path}'
        self.responses[key] = {
            'response': response,
            'status_code': status_code,
            'headers': {'Content-Type': 'application/json'},
        }

    def get_response(self, path: str, method: str) -> Dict[str, Any]:
        """Get response for a path and method."""
        key = f'{method.upper()}:{path}'

        # Try exact match first
        if key in self.responses:
            return self.responses[key]

        # Try to match without leading slash
        path_no_slash = path.lstrip('/')
        key_no_slash = f'{method.upper()}:/{path_no_slash}'
        if key_no_slash in self.responses:
            return self.responses[key_no_slash]

        # Try to match with leading slash
        if not path.startswith('/'):
            key_with_slash = f'{method.upper()}:/{path}'
            if key_with_slash in self.responses:
                return self.responses[key_with_slash]

        # Return default response
        return {
            'response': self.default_response,
            'status_code': 200,
            'headers': {'Content-Type': 'application/json'},
        }

    def log_request(
        self, method: str, url: str, headers: Dict[str, str], body: Any = None
    ):
        """Log incoming requests for verification."""
        self.request_log.append(
            {
                'method': method,
                'url': url,
                'headers': dict(headers),
                'body': body,
                'timestamp': '2024-01-01T00:00:00Z',
            }
        )

    def create_mock_response(
        self, method: str, url: str, headers: Dict[str, str], **kwargs
    ) -> Mock:
        """Create a mock HTTP response."""
        # Extract path from URL
        if url.startswith(self.base_url):
            path = url[len(self.base_url) :]
        else:
            # Handle cases where URL might be just a path
            from urllib.parse import urlparse

            parsed = urlparse(url)
            path = parsed.path

        # Ensure path starts with /
        if not path.startswith('/'):
            path = '/' + path

        # Log the request
        body = kwargs.get('json') or kwargs.get('content')
        self.log_request(method, url, headers, body)

        # Get configured response
        response_config = self.get_response(path, method)

        # Create mock response
        from unittest.mock import Mock
        import httpx

        mock_response = Mock()
        mock_response.status_code = response_config['status_code']
        mock_response.headers = response_config['headers']
        mock_response.json.return_value = response_config['response']
        mock_response.text = json.dumps(response_config['response'])

        # Configure raise_for_status to behave like real httpx
        def raise_for_status():
            if 400 <= mock_response.status_code < 600:
                raise httpx.HTTPStatusError(
                    f'{mock_response.status_code} Error',
                    request=Mock(),
                    response=mock_response,
                )

        mock_response.raise_for_status.side_effect = raise_for_status

        return mock_response


@pytest.fixture
def mock_backend():
    """Create a mock backend service."""
    return MockBackendService()


@pytest.fixture
def configured_mock_backend(mock_backend):
    """Mock backend with pre-configured responses."""
    # User management endpoints
    mock_backend.set_response(
        '/users',
        'GET',
        {
            'users': [
                {
                    'id': 1,
                    'name': 'John Doe',
                    'email': 'john@example.com',
                    'active': True,
                },
                {
                    'id': 2,
                    'name': 'Jane Smith',
                    'email': 'jane@example.com',
                    'active': True,
                },
            ],
            'total': 2,
            'page': 1,
        },
    )

    mock_backend.set_response(
        '/users',
        'POST',
        {
            'id': 3,
            'name': 'New User',
            'email': 'newuser@example.com',
            'active': True,
            'created_at': '2024-01-01T00:00:00Z',
        },
        status_code=201,
    )

    mock_backend.set_response(
        '/users/1',
        'GET',
        {
            'id': 1,
            'name': 'John Doe',
            'email': 'john@example.com',
            'active': True,
            'created_at': '2023-01-01T00:00:00Z',
            'orders': [
                {
                    'order_id': 'ORD001',
                    'order_date': '2024-01-01',
                    'order_total': 99.99,
                },
                {
                    'order_id': 'ORD002',
                    'order_date': '2024-01-02',
                    'order_total': 149.99,
                },
            ],
        },
    )

    # Orders endpoint with field mapping
    mock_backend.set_response(
        '/users/1/orders',
        'GET',
        {
            'orders': [
                {
                    'order_id': 'ORD001',
                    'order_date': '2024-01-01T10:00:00Z',
                    'order_total': 99.99,
                    'customer_info': {'name': 'John Doe', 'email': 'john@example.com'},
                    'items': [{'name': 'Product A', 'price': 99.99}],
                },
                {
                    'order_id': 'ORD002',
                    'order_date': '2024-01-02T15:30:00Z',
                    'order_total': 149.99,
                    'customer_info': {'name': 'John Doe', 'email': 'john@example.com'},
                    'items': [{'name': 'Product B', 'price': 149.99}],
                },
            ],
            'total_orders': 2,
        },
    )

    # Error responses
    mock_backend.set_response(
        '/users/999',
        'GET',
        {'error': 'User not found', 'code': 'USER_NOT_FOUND'},
        status_code=404,
    )

    return mock_backend


@pytest.fixture
def mock_httpx_with_backend(configured_mock_backend):
    """Mock httpx client that uses the configured backend."""

    async def mock_request(method, url, **kwargs):
        headers = kwargs.pop('headers', {})
        return configured_mock_backend.create_mock_response(
            method, url, headers, **kwargs
        )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_client.request.side_effect = mock_request
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client
        yield mock_client, configured_mock_backend


class TestFullIntegrationWithMockBackend:
    """Full integration tests with mock backend services."""

    @pytest.mark.asyncio
    async def test_bearer_auth_integration(self, api_proxy, mock_httpx_with_backend):
        """Test full integration with Bearer authentication."""
        mock_client, mock_backend = mock_httpx_with_backend

        # Process request through API proxy
        response = await api_proxy.process_request(
            service_id='yaml-test-service',
            api_id='yaml-api',
            api_version='v1',
            method='POST',
            path='/test',
            query_params={'limit': '10'},
            headers={'User-Agent': 'integration-test'},
            body={'filter': 'active'},
        )

        # Verify response structure
        assert response.meta['status'] == 'success'
        assert 'trace' in response.meta
        assert response.data is not None

        # Verify authentication was applied
        assert len(mock_backend.request_log) > 0
        request = mock_backend.request_log[0]
        assert 'Authorization' in request['headers']
        assert request['headers']['Authorization'] == 'Bearer yaml-test-token'

        # Verify additional headers were added
        assert 'X-YAML-Test' in request['headers']
        assert request['headers']['X-YAML-Test'] == 'true'

    @pytest.mark.asyncio
    async def test_get_users_with_bearer_auth(self, api_proxy, mock_httpx_with_backend):
        """Test GET users endpoint with Bearer authentication."""
        mock_client, mock_backend = mock_httpx_with_backend

        # Configure mock backend for this specific test
        mock_backend.base_url = 'https://api.yaml-test.com'

        # Set up the specific response for the path that will be called
        mock_backend.set_response(
            '/yaml/test',
            'GET',
            {
                'users': [
                    {'id': 1, 'name': 'John Doe', 'email': 'john@example.com'},
                    {'id': 2, 'name': 'Jane Smith', 'email': 'jane@example.com'},
                ],
                'total': 2,
            },
        )

        response = await api_proxy.process_request(
            service_id='yaml-test-service',
            api_id='yaml-api',
            api_version='v1',
            method='POST',  # Client always uses POST
            path='/users',
            query_params={'page': '1', 'limit': '10'},
            headers={'User-Agent': 'test-client'},
            body={},
        )

        # Verify successful response
        assert response.meta['status'] == 'success'
        assert response.data['users'] is not None
        assert len(response.data['users']) == 2

        # Verify request was logged with correct authentication
        request = mock_backend.request_log[-1]
        assert request['method'] == 'GET'  # Backend method from config
        assert 'Authorization' in request['headers']
        assert request['headers']['Authorization'] == 'Bearer yaml-test-token'

    @pytest.mark.asyncio
    async def test_create_user_with_auth_headers(
        self, api_proxy, mock_httpx_with_backend
    ):
        """Test POST create user with authentication and custom headers."""
        mock_client, mock_backend = mock_httpx_with_backend
        mock_backend.base_url = 'https://api.yaml-test.com'

        # Set up the specific response for the path that will be called
        mock_backend.set_response(
            '/yaml/test',
            'GET',
            {
                'id': 3,
                'name': 'New User',
                'email': 'testuser@example.com',
                'created_at': '2024-01-01T00:00:00Z',
            },
        )

        user_data = {'name': 'Test User', 'email': 'testuser@example.com'}

        response = await api_proxy.process_request(
            service_id='yaml-test-service',
            api_id='yaml-api',
            api_version='v1',
            method='POST',
            path='/users',
            headers={'Content-Type': 'application/json'},
            body=user_data,
        )

        # Verify response
        assert response.meta['status'] == 'success'
        assert response.data['id'] == 3
        assert response.data['name'] == 'New User'

        # Verify request details
        request = mock_backend.request_log[-1]
        assert request['method'] == 'GET'  # From YAML config
        # Note: GET requests typically don't have bodies, so we verify the auth instead
        assert 'Authorization' in request['headers']
        assert request['headers']['Authorization'] == 'Bearer yaml-test-token'

    @pytest.mark.asyncio
    async def test_output_mapping_integration(
        self, sample_service_definition, mock_httpx_with_backend
    ):
        """Test output field mapping with mock backend."""
        from api_services_module.core.proxy import ApiProxy
        from api_services_module.config.registry import ServiceRegistry

        mock_client, mock_backend = mock_httpx_with_backend
        mock_backend.base_url = 'https://api.test-service.com'

        # Set up the response with data that will be mapped
        mock_backend.set_response(
            '/users/{id}/orders',
            'GET',
            {
                'order_id': 'ORD001',
                'order_date': '2024-01-01T10:00:00Z',
                'customer': {'name': 'John Doe'},
            },
        )

        # Create service registry with our test service
        registry = ServiceRegistry()
        registry.register_service(sample_service_definition)

        # Create API proxy
        proxy = ApiProxy(registry)

        response = await proxy.process_request(
            service_id='test-service',
            api_id='get-user-orders',
            api_version='v1',
            method='POST',
            path='/users/1/orders',
            headers={'Accept': 'application/json'},
            body={},
        )

        # Verify response structure
        assert response.meta['status'] == 'success'

        # Verify output mapping was applied
        mapped_data = response.data
        assert 'id' in mapped_data  # Mapped from order_id
        assert 'created_at' in mapped_data  # Mapped from order_date
        assert 'customer_name' in mapped_data  # Mapped from customer.name

        # Verify authentication
        request = mock_backend.request_log[-1]
        assert 'Authorization' in request['headers']
        assert request['headers']['Authorization'] == 'Bearer test-bearer-token-123'

    @pytest.mark.asyncio
    async def test_error_handling_integration(self, api_proxy, mock_httpx_with_backend):
        """Test error handling with 500 response from backend."""
        mock_client, mock_backend = mock_httpx_with_backend
        mock_backend.base_url = 'https://api.yaml-test.com'

        # Configure 500 response to trigger pipeline error
        mock_backend.set_response(
            '/yaml/test', 'GET', {'error': 'Server Error'}, status_code=500
        )

        response = await api_proxy.process_request(
            service_id='yaml-test-service',
            api_id='yaml-api',
            api_version='v1',
            method='POST',
            path='/users/999',  # This path is ignored/mapped to /yaml/test by the API config
            headers={'Accept': 'application/json'},
            body={},
        )

        # Should return error response
        assert response.meta['status'] in [
            'pipeline_error',
            'error',
            'api_pipeline_error',
        ]
        assert 'trace' in response.meta

    @pytest.mark.asyncio
    async def test_multiple_auth_types_integration(self, mock_httpx_with_backend):
        """Test integration with different authentication types."""
        from api_services_module.config.registry import ServiceRegistry
        from api_services_module.core.proxy import ApiProxy
        from api_services_module.models.service import (
            ServiceDefinition,
            AuthConfig,
            ApiConfig,
        )

        mock_client, mock_backend = mock_httpx_with_backend

        # Create services with different auth types
        services = []

        # Bearer auth service
        bearer_service = ServiceDefinition(
            id='bearer-service',
            base_url='https://api.bearer-test.com',
            auth=AuthConfig(
                id='bearer-auth', type=AuthType.BEARER, token='bearer-token-123'
            ),
            apis=[
                ApiConfig(
                    id='test-api',
                    path='/test',
                    method=HttpMethod.GET,
                    backend_path='/test',
                )
            ],
        )
        services.append(bearer_service)

        # Basic auth service
        basic_service = ServiceDefinition(
            id='basic-service',
            base_url='https://api.basic-test.com',
            auth=AuthConfig(
                id='basic-auth',
                type=AuthType.BASIC,
                username='testuser',
                password='testpass',
            ),
            apis=[
                ApiConfig(
                    id='test-api',
                    path='/test',
                    backend_path='/test',
                    method=HttpMethod.GET,
                )
            ],
        )
        services.append(basic_service)

        # API Key service
        apikey_service = ServiceDefinition(
            id='apikey-service',
            base_url='https://api.apikey-test.com',
            auth=AuthConfig(
                id='apikey-auth',
                type=AuthType.API_KEY,
                api_key='apikey-123',
                api_key_header='X-API-Key',
            ),
            apis=[
                ApiConfig(
                    id='test-api',
                    path='/test',
                    backend_path='/test',
                    method=HttpMethod.GET,
                )
            ],
        )
        services.append(apikey_service)

        # Create registry and proxy
        registry = ServiceRegistry()
        for service in services:
            registry.register_service(service)

        proxy = ApiProxy(registry)

        # Test each auth type
        for service in services:
            mock_backend.base_url = service.base_url

            response = await proxy.process_request(
                service_id=service.id,
                api_id='test-api',
                api_version='v1',
                method='POST',
                path='/test',
                headers={'Accept': 'application/json'},
                body={},
            )

            assert response.meta['status'] == 'success'

            # Verify correct authentication header
            request = mock_backend.request_log[-1]

            if service.auth.type == AuthType.BEARER:
                assert request['headers']['Authorization'] == 'Bearer bearer-token-123'
            elif service.auth.type == AuthType.BASIC:
                import base64

                expected = base64.b64encode('testuser:testpass'.encode()).decode()
                assert request['headers']['Authorization'] == f'Basic {expected}'
            elif service.auth.type == AuthType.API_KEY:
                assert request['headers']['X-API-Key'] == 'apikey-123'

    def test_pipeline_execution_trace(self, api_proxy, mock_httpx_with_backend):
        """Test that pipeline execution trace is properly recorded."""
        mock_client, mock_backend = mock_httpx_with_backend

        # Use asyncio.run for this test since it's not marked as async
        async def run_test():
            response = await api_proxy.process_request(
                service_id='yaml-test-service',
                api_id='yaml-api',
                api_version='v1',
                method='POST',
                path='/test',
                headers={'User-Agent': 'trace-test'},
                body={'test': 'trace'},
            )

            # Verify trace contains expected stages
            trace = response.meta['trace']
            assert len(trace) > 0

            # Check for key pipeline stages in trace
            trace_text = ' '.join(trace)
            assert 'auth_pipeline' in trace_text
            assert (
                'bearer_authenticator' in trace_text or 'Authentication' in trace_text
            )
            assert 'request_sender' in trace_text or 'Request' in trace_text

            return response

        response = asyncio.run(run_test())
        assert response.meta['status'] == 'success'

    @pytest.mark.asyncio
    async def test_concurrent_requests_integration(
        self, api_proxy, mock_httpx_with_backend
    ):
        """Test handling multiple concurrent requests."""
        mock_client, mock_backend = mock_httpx_with_backend
        mock_backend.base_url = 'https://api.yaml-test.com'

        # Create multiple concurrent requests
        tasks = []
        for i in range(5):
            task = api_proxy.process_request(
                service_id='yaml-test-service',
                api_id='yaml-api',
                api_version='v1',
                method='POST',
                path=f'/users/{i}',
                headers={'User-Agent': f'concurrent-test-{i}'},
                body={'user_id': i},
            )
            tasks.append(task)

        # Execute all requests concurrently
        responses = await asyncio.gather(*tasks)

        # Verify all requests succeeded
        for i, response in enumerate(responses):
            assert response.meta['status'] == 'success'

        # Verify all requests were logged
        assert len(mock_backend.request_log) >= 5

        # Verify each request had proper authentication
        for request in mock_backend.request_log[-5:]:
            assert 'Authorization' in request['headers']
            assert request['headers']['Authorization'] == 'Bearer yaml-test-token'


class TestFastAPIIntegration:
    """Test integration with FastAPI test client."""

    def test_fastapi_router_integration(self, test_client, mock_httpx_with_backend):
        """Test the FastAPI router with mock backend."""
        mock_client, mock_backend = mock_httpx_with_backend
        mock_backend.base_url = 'https://api.yaml-test.com'

        # Test services list
        response = test_client.get('/v1/api-services')
        assert response.status_code == 200
        data = response.json()
        assert 'services' in data['data']

        # Test specific service info (use a service that exists in real configs)
        response = test_client.get('/v1/api-services/crm-service')
        assert response.status_code == 200
        data = response.json()
        assert data['data']['service_id'] == 'crm-service'

    def test_proxy_endpoint_integration(self, test_client, mock_httpx_with_backend):
        """Test the main proxy endpoint with FastAPI client."""
        mock_client, mock_backend = mock_httpx_with_backend
        mock_backend.base_url = 'https://api.crm-system.com'

        # Set up mock response for CRM service
        mock_backend.set_response(
            '/customers',
            'GET',
            {'customers': [{'id': 1, 'name': 'Test Customer'}], 'total': 1},
        )

        # Test proxy request (use real service from configs)
        # Using main path-based route (alias routes have been removed)
        response = test_client.post(
            '/v1/api-services/crm-service/apis/v1/customers',
            json={'test': 'data'},
            headers={'Content-Type': 'application/json'},
        )

        assert response.status_code == 200
        data = response.json()
        assert data['meta']['status'] == 'success'
        assert 'trace' in data['meta']
        assert data['data'] is not None

        # Verify backend received the request
        assert len(mock_backend.request_log) > 0
        request = mock_backend.request_log[-1]
        assert 'Authorization' in request['headers']


# Performance and load testing fixtures
@pytest.fixture
def performance_mock_backend():
    """Mock backend optimized for performance testing."""
    backend = MockBackendService()

    # Set up fast responses
    for i in range(100):
        backend.set_response(
            f'/users/{i}',
            'GET',
            {'id': i, 'name': f'User {i}', 'email': f'user{i}@example.com'},
        )

    return backend


class TestPerformanceIntegration:
    """Performance and load testing with mock backend."""

    @pytest.mark.asyncio
    async def test_high_throughput_requests(self, api_proxy, performance_mock_backend):
        """Test handling high throughput requests."""
        with patch('httpx.AsyncClient') as mock_client_class:
            from unittest.mock import MagicMock, AsyncMock

            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            async def async_side_effect(method, url, **kwargs):
                headers = kwargs.pop('headers', {})
                return performance_mock_backend.create_mock_response(
                    method, url, headers, **kwargs
                )

            mock_client.request.side_effect = async_side_effect

            mock_client_class.return_value = mock_client

            # Create many concurrent requests
            tasks = []
            for i in range(50):  # Reduced for test performance
                task = api_proxy.process_request(
                    service_id='yaml-test-service',
                    api_id='yaml-api',
                    api_version='v1',
                    method='POST',
                    path=f'/users/{i}',
                    headers={'User-Agent': 'performance-test'},
                    body={'user_id': i},
                )
                tasks.append(task)

            # Measure execution time
            import time

            start_time = time.time()
            responses = await asyncio.gather(*tasks)
            end_time = time.time()

            # Verify all requests succeeded
            success_count = sum(1 for r in responses if r.meta['status'] == 'success')
            assert success_count == 50

            # Basic performance assertion (should complete in reasonable time)
            execution_time = end_time - start_time
            assert execution_time < 10.0  # Should complete within 10 seconds

            print(f'Processed 50 requests in {execution_time:.2f} seconds')
            print(f'Average: {execution_time/50*1000:.2f}ms per request')
