"""
Simple integration test with mock backend for API Services Module.

This test demonstrates the core integration functionality with a
straightforward mock backend setup.
"""

import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock, AsyncMock
import base64

from api_services_module.models.service import (
    ServiceDefinition,
    AuthConfig,
    ApiConfig,
    AuthType,
    HttpMethod,
)
from api_services_module.config.registry import ServiceRegistry
from api_services_module.core.proxy import ApiProxy


class SimpleMockBackend:
    """Simple mock backend for integration testing."""

    def __init__(self):
        self.requests = []
        self.response_data = {
            'success': True,
            'message': 'Mock backend response',
            'timestamp': '2024-01-01T00:00:00Z',
        }

    def create_response(self, method: str, url: str, headers: dict, **kwargs):
        """Create a mock HTTP response and log the request."""
        # Log the request for verification
        self.requests.append(
            {
                'method': method,
                'url': url,
                'headers': dict(headers),
                'body': kwargs.get('json') or kwargs.get('content'),
            }
        )

        # Create mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'application/json'}
        mock_response.json.return_value = self.response_data
        mock_response.text = json.dumps(self.response_data)
        mock_response.raise_for_status.return_value = None

        return mock_response


@pytest.fixture
def simple_mock_backend():
    """Create a simple mock backend."""
    return SimpleMockBackend()


@pytest.fixture
def bearer_service():
    """Create a service with Bearer authentication."""
    return ServiceDefinition(
        id='test-bearer-service',
        base_url='https://api.bearer-test.com',
        auth=AuthConfig(
            id='bearer-auth',
            type=AuthType.BEARER,
            token='test-bearer-token-123',
            additional_headers={'X-Client-ID': 'test-client'},
        ),
        apis=[
            ApiConfig(
                id='get-data',
                path='/data',
                backend_path='/data',
                method=HttpMethod.GET,
                additional_headers={'X-API-Feature': 'data-retrieval'},
            ),
            ApiConfig(
                id='create-item',
                path='/items',
                backend_path='/items',
                method=HttpMethod.POST,
                additional_headers={'X-API-Feature': 'item-creation'},
            ),
        ],
    )


@pytest.fixture
def basic_service():
    """Create a service with Basic authentication."""
    return ServiceDefinition(
        id='test-basic-service',
        base_url='https://api.basic-test.com',
        auth=AuthConfig(
            id='basic-auth',
            type=AuthType.BASIC,
            username='testuser',
            password='testpass123',
        ),
        apis=[
            ApiConfig(
                id='get-users',
                path='/users',
                backend_path='/users',
                method=HttpMethod.GET,
            )
        ],
    )


@pytest.fixture
def apikey_service():
    """Create a service with API Key authentication."""
    return ServiceDefinition(
        id='test-apikey-service',
        base_url='https://api.apikey-test.com',
        auth=AuthConfig(
            id='apikey-auth',
            type=AuthType.API_KEY,
            api_key='secret-api-key-456',
            api_key_header='X-API-Key',
        ),
        apis=[
            ApiConfig(
                id='get-status',
                path='/status',
                backend_path='/status',
                method=HttpMethod.GET,
            )
        ],
    )


@pytest.fixture
def test_registry(bearer_service, basic_service, apikey_service):
    """Create a service registry with test services."""
    registry = ServiceRegistry()
    registry.register_service(bearer_service)
    registry.register_service(basic_service)
    registry.register_service(apikey_service)
    return registry


@pytest.fixture
def test_proxy(test_registry):
    """Create an API proxy with test services."""
    return ApiProxy(test_registry)


class TestSimpleIntegration:
    """Simple integration tests with mock backend."""

    @pytest.mark.asyncio
    async def test_bearer_auth_integration(self, test_proxy, simple_mock_backend):
        """Test Bearer authentication integration."""

        with patch('httpx.AsyncClient') as mock_client_class:
            # Setup mock client
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            async def async_side_effect(method, url, **kwargs):
                headers = kwargs.pop('headers', {})
                return simple_mock_backend.create_response(
                    method, url, headers, **kwargs
                )

            mock_client.request.side_effect = async_side_effect
            mock_client_class.return_value = mock_client

            # Make request through proxy
            response = await test_proxy.process_request(
                service_id='test-bearer-service',
                api_id='get-data',
                api_version='v1',
                method='POST',  # Client method
                path='/test-path',
                query_params={'limit': '10'},
                headers={'User-Agent': 'test-client'},
                body={'filter': 'active'},
            )

            # Verify response
            assert response.meta['status'] == 'success'
            assert response.data['success'] is True
            assert 'trace' in response.meta

            # Verify request was made with correct authentication
            assert len(simple_mock_backend.requests) == 1
            request = simple_mock_backend.requests[0]

            # Check authentication header
            assert 'Authorization' in request['headers']
            assert request['headers']['Authorization'] == 'Bearer test-bearer-token-123'

            # Check additional headers
            assert request['headers']['X-Client-ID'] == 'test-client'
            assert request['headers']['X-API-Feature'] == 'data-retrieval'

            # Check method mapping (POST from client -> GET to backend)
            assert request['method'] == 'GET'

            # Check URL construction
            assert 'https://api.bearer-test.com/data' in request['url']

    @pytest.mark.asyncio
    async def test_basic_auth_integration(self, test_proxy, simple_mock_backend):
        """Test Basic authentication integration."""

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            async def async_side_effect(method, url, **kwargs):
                headers = kwargs.pop('headers', {})
                return simple_mock_backend.create_response(
                    method, url, headers, **kwargs
                )

            mock_client.request.side_effect = async_side_effect
            mock_client_class.return_value = mock_client

            response = await test_proxy.process_request(
                service_id='test-basic-service',
                api_id='get-users',
                api_version='v1',
                method='POST',
                path='/users',
                headers={'Accept': 'application/json'},
                body={},
            )

            # Verify response
            assert response.meta['status'] == 'success'

            # Verify Basic auth header
            request = simple_mock_backend.requests[0]
            assert 'Authorization' in request['headers']

            # Verify Basic auth encoding
            expected_credentials = base64.b64encode(
                'testuser:testpass123'.encode()
            ).decode()
            assert (
                request['headers']['Authorization'] == f'Basic {expected_credentials}'
            )

    @pytest.mark.asyncio
    async def test_api_key_auth_integration(self, test_proxy, simple_mock_backend):
        """Test API Key authentication integration."""

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            async def async_side_effect(method, url, **kwargs):
                headers = kwargs.pop('headers', {})
                return simple_mock_backend.create_response(
                    method, url, headers, **kwargs
                )

            mock_client.request.side_effect = async_side_effect
            mock_client_class.return_value = mock_client

            response = await test_proxy.process_request(
                service_id='test-apikey-service',
                api_id='get-status',
                api_version='v1',
                method='POST',
                path='/status',
                headers={'Accept': 'application/json'},
                body={},
            )

            # Verify response
            assert response.meta['status'] == 'success'

            # Verify API Key header
            request = simple_mock_backend.requests[0]
            assert 'X-API-Key' in request['headers']
            assert request['headers']['X-API-Key'] == 'secret-api-key-456'

    @pytest.mark.asyncio
    async def test_pipeline_execution_trace(self, test_proxy, simple_mock_backend):
        """Test that pipeline execution is properly traced."""

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            async def async_side_effect(method, url, **kwargs):
                headers = kwargs.pop('headers', {})
                return simple_mock_backend.create_response(
                    method, url, headers, **kwargs
                )

            mock_client.request.side_effect = async_side_effect
            mock_client_class.return_value = mock_client

            response = await test_proxy.process_request(
                service_id='test-bearer-service',
                api_id='get-data',
                api_version='v1',
                method='POST',
                path='/data',
                headers={'User-Agent': 'trace-test'},
                body={'test': 'trace'},
            )

            # Verify trace contains expected pipeline stages
            trace = response.meta['trace']
            assert len(trace) > 0

            trace_text = ' '.join(trace)

            # Check for key pipeline stages
            assert 'proxy' in trace_text.lower()
            assert any('auth' in entry.lower() for entry in trace)
            assert any('request' in entry.lower() for entry in trace)

    @pytest.mark.asyncio
    async def test_error_handling_integration(self, test_proxy):
        """Test error handling when backend is unreachable."""

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            # Simulate network error
            import httpx

            mock_client.request.side_effect = httpx.ConnectError('Connection failed')
            mock_client_class.return_value = mock_client

            response = await test_proxy.process_request(
                service_id='test-bearer-service',
                api_id='get-data',
                api_version='v1',
                method='POST',
                path='/data',
                headers={'User-Agent': 'error-test'},
                body={},
            )

            # Should return error response, not raise exception
            assert response.meta['status'] in [
                'pipeline_error',
                'error',
                'api_pipeline_error',
            ]
            assert 'trace' in response.meta
            assert (
                'Connection failed' in response.meta['message']
                or 'Backend request failed' in response.meta['message']
            )

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, test_proxy, simple_mock_backend):
        """Test handling multiple concurrent requests."""

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            async def async_side_effect(method, url, **kwargs):
                headers = kwargs.pop('headers', {})
                return simple_mock_backend.create_response(
                    method, url, headers, **kwargs
                )

            mock_client.request.side_effect = async_side_effect
            mock_client_class.return_value = mock_client

            # Create multiple concurrent requests
            tasks = []
            for i in range(5):
                task = test_proxy.process_request(
                    service_id='test-bearer-service',
                    api_id='get-data',
                    api_version='v1',
                    method='POST',
                    path=f'/data/{i}',
                    headers={'User-Agent': f'concurrent-test-{i}'},
                    body={'request_id': i},
                )
                tasks.append(task)

            # Execute all requests concurrently
            responses = await asyncio.gather(*tasks)

            # Verify all requests succeeded
            for response in responses:
                assert response.meta['status'] == 'success'

            # Verify all requests were logged
            assert len(simple_mock_backend.requests) == 5

            # Verify each request had proper authentication
            for request in simple_mock_backend.requests:
                assert (
                    request['headers']['Authorization']
                    == 'Bearer test-bearer-token-123'
                )

    def test_service_registry_integration(self, test_registry):
        """Test service registry functionality."""
        # Verify services are registered
        assert len(test_registry.get_service_ids()) == 3

        # Test service retrieval
        bearer_service = test_registry.get_service('test-bearer-service')
        assert bearer_service is not None
        assert bearer_service.auth.type == AuthType.BEARER

        # Test API retrieval
        api = bearer_service.get_api_by_id('get-data')
        assert api is not None
        assert api.method == HttpMethod.GET

        # Test validation
        for service_id in test_registry.get_service_ids():
            assert test_registry.validate_service(service_id)

    def test_proxy_health_check(self, test_proxy):
        """Test proxy health check functionality."""
        health = test_proxy.health_check()

        assert health['status'] == 'healthy'
        assert health['services_count'] == 3
        assert health['apis_count'] == 4  # Total APIs across all services
        assert 'bearer' in health['auth_types_supported']
        assert 'basic' in health['auth_types_supported']
        assert 'api_key' in health['auth_types_supported']


class TestServiceConfiguration:
    """Test service configuration and validation."""

    def test_bearer_service_config(self, bearer_service):
        """Test Bearer service configuration."""
        assert bearer_service.id == 'test-bearer-service'
        assert bearer_service.auth.type == AuthType.BEARER
        assert bearer_service.auth.token == 'test-bearer-token-123'
        assert len(bearer_service.apis) == 2

    def test_basic_service_config(self, basic_service):
        """Test Basic service configuration."""
        assert basic_service.id == 'test-basic-service'
        assert basic_service.auth.type == AuthType.BASIC
        assert basic_service.auth.username == 'testuser'
        assert basic_service.auth.password == 'testpass123'

    def test_apikey_service_config(self, apikey_service):
        """Test API Key service configuration."""
        assert apikey_service.id == 'test-apikey-service'
        assert apikey_service.auth.type == AuthType.API_KEY
        assert apikey_service.auth.api_key == 'secret-api-key-456'
        assert apikey_service.auth.api_key_header == 'X-API-Key'


class TestPipelineComponents:
    """Test individual pipeline components."""

    @pytest.mark.asyncio
    async def test_auth_pipeline_execution(self, test_proxy, simple_mock_backend):
        """Test authentication pipeline execution."""

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            async def async_side_effect(method, url, **kwargs):
                headers = kwargs.pop('headers', {})
                return simple_mock_backend.create_response(
                    method, url, headers, **kwargs
                )

            mock_client.request.side_effect = async_side_effect
            mock_client_class.return_value = mock_client

            # Test each auth type
            test_cases = [
                ('test-bearer-service', 'get-data', 'Bearer test-bearer-token-123'),
                (
                    'test-apikey-service',
                    'get-status',
                    None,
                ),  # API key uses different header
            ]

            for service_id, api_id, expected_auth in test_cases:
                simple_mock_backend.requests.clear()

                response = await test_proxy.process_request(
                    service_id=service_id,
                    api_id=api_id,
                    api_version='v1',
                    method='POST',
                    path='/test',
                    headers={'User-Agent': 'auth-test'},
                    body={},
                )

                assert response.meta['status'] == 'success'

                request = simple_mock_backend.requests[0]
                if expected_auth:
                    assert request['headers']['Authorization'] == expected_auth
                else:
                    # API key case
                    assert 'X-API-Key' in request['headers']


# Performance test
class TestPerformance:
    """Basic performance tests."""

    @pytest.mark.asyncio
    async def test_throughput(self, test_proxy, simple_mock_backend):
        """Test basic throughput with mock backend."""

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            async def async_side_effect(method, url, **kwargs):
                headers = kwargs.pop('headers', {})
                return simple_mock_backend.create_response(
                    method, url, headers, **kwargs
                )

            mock_client.request.side_effect = async_side_effect
            mock_client_class.return_value = mock_client

            # Measure time for batch of requests
            import time

            start_time = time.time()

            tasks = []
            for i in range(20):  # Smaller batch for test performance
                task = test_proxy.process_request(
                    service_id='test-bearer-service',
                    api_id='get-data',
                    api_version='v1',
                    method='POST',
                    path=f'/perf-test/{i}',
                    headers={'User-Agent': 'perf-test'},
                    body={'test_id': i},
                )
                tasks.append(task)

            responses = await asyncio.gather(*tasks)
            end_time = time.time()

            # Verify all succeeded
            success_count = sum(1 for r in responses if r.meta['status'] == 'success')
            assert success_count == 20

            # Basic performance check
            execution_time = end_time - start_time
            assert execution_time < 5.0  # Should complete within 5 seconds

            print(f'Processed 20 requests in {execution_time:.2f} seconds')
            print(f'Average: {execution_time/20*1000:.2f}ms per request')
