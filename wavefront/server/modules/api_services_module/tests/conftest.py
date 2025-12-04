"""
Pytest configuration and fixtures for API Services Module.

This file provides reusable fixtures for testing the API services module
components including containers, services, authentication, and pipelines.
"""

import pytest
from unittest.mock import Mock
from io import BytesIO
from typing import Dict, Any
import yaml
from dependency_injector import providers

from api_services_module.api_services_container import create_api_services_container
from api_services_module.config.registry import ServiceRegistry
from api_services_module.config.parser import ServiceDefinitionParser
from api_services_module.auth.manager import AuthManager
from api_services_module.core.proxy import ApiProxy
from api_services_module.core.router import ProxyRouter
from api_services_module.models.service import (
    ServiceDefinition,
    AuthConfig,
    ApiConfig,
    AuthType,
    HttpMethod,
)
from api_services_module.models.pipeline import PipelineContext
from api_services_module.pipeline.builder import PipelineBuilder, PipelineCache
from common_module.models.response import Meta
from common_module.models.response import ResponseModel


# ============================================================================
# Mock Dependencies
# ============================================================================


class MockDatabaseClient:
    """Mock database client for testing."""

    def __init__(self):
        self.connected = False
        self.migration_run = False

    async def connect(self):
        """Mock connect method."""
        self.connected = True

    def run_migration(self):
        """Mock migration method."""
        self.migration_run = True

    def is_connected(self) -> bool:
        """Check if connected."""
        return self.connected


class MockCacheManager:
    """Mock cache manager for testing."""

    def __init__(self):
        self._cache: Dict[str, Any] = {}

    def get(self, key: str):
        """Mock get method."""
        return self._cache.get(key)

    def set(self, key: str, value: Any, ttl: int = None):
        """Mock set method."""
        self._cache[key] = value

    def add(self, key: str, value: Any, ttl: int = None):
        """Alias for cache add to match production interface."""
        self.set(key, value, ttl)

    def delete(self, key: str):
        """Mock delete method."""
        self._cache.pop(key, None)

    def clear(self):
        """Clear all cached items."""
        self._cache.clear()

    def get_str(self, key: str):
        """Return cached string value."""
        value = self.get(key)
        if value is None:
            return None
        return value


class MockCloudStorageManager:
    """Mock cloud storage manager for testing."""

    def __init__(self):
        self._storage: Dict[str, bytes] = {}
        self.last_saved: Dict[str, Dict[str, Any]] = {}

    def save_small_file(
        self, file_content: bytes, bucket_name: str, key: str, content_type: str
    ):
        """Mock save small file."""
        self._storage[key] = file_content
        self.last_saved[key] = {
            'bucket': bucket_name,
            'content_type': content_type,
        }

    def read_file(self, bucket_name: str, file_path: str) -> BytesIO:
        """Mock read file."""
        data = self._storage.get(file_path, b'')
        return BytesIO(data)

    def delete_file(self, bucket_name: str, file_path: str):
        """Mock delete file."""
        self._storage.pop(file_path, None)


class MockApiServiceRecord:
    """Lightweight API service record."""

    def __init__(self, service_id: str):
        self.id = service_id
        self.service_def_path = f'api_services/{service_id}.yaml'
        self.is_active = True


class MockApiServicesRepository:
    """In-memory repository for API services metadata."""

    def __init__(self):
        self._data: Dict[str, MockApiServiceRecord] = {}

    def create(self, **kwargs):
        record = MockApiServiceRecord(kwargs['id'])
        self._data[record.id] = record
        return record

    def find_one(self, id: str):
        return self._data.get(id)

    def find(self):
        return list(self._data.values())

    def find_one_and_update(self, filters: Dict[str, Any], update_data: Dict[str, Any]):
        record = self._data.get(filters.get('id'))
        if not record:
            return None
        for key, value in update_data.items():
            setattr(record, key, value)
        return record

    def delete_all(self, filters: Dict[str, Any]):
        self._data.pop(filters.get('id'), None)


class MockApiServicesManager:
    """Mock ApiServicesManager that sources YAML from in-memory map."""

    def __init__(self, service_yaml_map: Dict[str, str]):
        self._yaml_map = service_yaml_map
        self._repository = MockApiServicesRepository()
        for service_id in self._yaml_map.keys():
            self._repository.create(id=service_id, service_def_path='')

    async def get_all_api_services(self):
        return self._repository.find()

    def fetch_service_def(self, service_record):
        return self._yaml_map[service_record.id]

    async def get_api_service(self, id: str):
        return self._repository.find_one(id=id)

    async def create_api_service(self, id: str, service_def_yaml: str):
        self._yaml_map[id] = service_def_yaml
        return self._repository.create(id=id, service_def_path='')

    def update_api_service(self, id: str, service_def_yaml: str):
        self._yaml_map[id] = service_def_yaml
        return self._repository.find_one(id=id)

    async def delete_api_service(self, id: str):
        self._yaml_map.pop(id, None)
        self._repository.delete_all({'id': id})


@pytest.fixture
def mock_db_client():
    """Provide a mock database client."""
    return MockDatabaseClient()


@pytest.fixture
def mock_cache_manager():
    """Provide a mock cache manager."""
    return MockCacheManager()


# ============================================================================
# Service Definition Fixtures
# ============================================================================


@pytest.fixture
def sample_bearer_auth_config():
    """Sample Bearer authentication configuration."""
    return AuthConfig(
        id='test-bearer-auth',
        type=AuthType.BEARER,
        version='v1',
        token='test-bearer-token-123',
        additional_headers={'X-Client-ID': 'test-client'},
    )


@pytest.fixture
def sample_basic_auth_config():
    """Sample Basic authentication configuration."""
    return AuthConfig(
        id='test-basic-auth',
        type=AuthType.BASIC,
        version='v1',
        username='test_user',
        password='test_password',
        additional_headers={'X-Auth-Type': 'basic'},
    )


@pytest.fixture
def sample_api_key_auth_config():
    """Sample API Key authentication configuration."""
    return AuthConfig(
        id='test-apikey-auth',
        type=AuthType.API_KEY,
        version='v1',
        api_key='test-api-key-456',
        api_key_header='X-API-Key',
        additional_headers={'X-Service': 'test'},
    )


@pytest.fixture
def sample_api_configs():
    """Sample API configurations."""
    return [
        ApiConfig(
            id='get-users',
            path='/users',
            backend_path='/users',
            method=HttpMethod.GET,
            version='v1',
            additional_headers={'X-Feature': 'user-list'},
        ),
        ApiConfig(
            id='create-user',
            path='/users',
            backend_path='/users',
            method=HttpMethod.POST,
            version='v1',
            additional_headers={'X-Feature': 'user-create'},
        ),
        ApiConfig(
            id='get-user-orders',
            path='/users/{id}/orders',
            backend_path='/users/{id}/orders',
            method=HttpMethod.GET,
            version='v1',
            output_mapper_enabled=True,
            output_mapper={
                'order_id': 'id',
                'order_date': 'created_at',
                'customer.name': 'customer_name',
            },
        ),
    ]


@pytest.fixture
def sample_service_definition(sample_bearer_auth_config, sample_api_configs):
    """Sample service definition with Bearer auth."""
    return ServiceDefinition(
        id='test-service',
        base_url='https://api.test-service.com',
        auth=sample_bearer_auth_config,
        apis=sample_api_configs,
    )


@pytest.fixture
def sample_basic_service_definition(sample_basic_auth_config, sample_api_configs):
    """Sample service definition with Basic auth."""
    return ServiceDefinition(
        id='test-basic-service',
        base_url='https://api.basic-service.com',
        auth=sample_basic_auth_config,
        apis=sample_api_configs,
    )


@pytest.fixture
def sample_apikey_service_definition(sample_api_key_auth_config, sample_api_configs):
    """Sample service definition with API Key auth."""
    return ServiceDefinition(
        id='test-apikey-service',
        base_url='https://api.apikey-service.com',
        auth=sample_api_key_auth_config,
        apis=sample_api_configs,
    )


# ============================================================================
# YAML Configuration Fixtures
# ============================================================================


@pytest.fixture
def sample_yaml_config():
    """Sample YAML service configuration."""
    return {
        'service': {
            'id': 'yaml-test-service',
            'base_url': 'https://api.yaml-test.com',
            'auth': {
                'id': 'yaml-auth',
                'type': 'bearer',
                'version': 'v1',
                'token': 'yaml-test-token',
                'additional_headers': {'X-YAML-Test': 'true'},
            },
            'apis': [
                {
                    'id': 'yaml-api',
                    'path': '/yaml/test',
                    'backend_path': '/yaml/test',
                    'method': 'GET',
                    'version': 'v1',
                    'additional_headers': {'X-API-Test': 'yaml'},
                }
            ],
        }
    }


@pytest.fixture
def sample_service_yaml_map(sample_yaml_config):
    """Sample service definitions stored as YAML strings."""
    another_config = {
        'service': {
            'id': 'another-service',
            'base_url': 'https://api.another.com',
            'auth': {
                'id': 'another-auth',
                'type': 'basic',
                'username': 'user',
                'password': 'pass',
            },
            'apis': [
                {
                    'id': 'another-api',
                    'path': '/another',
                    'backend_path': '/another',
                    'method': 'POST',
                }
            ],
        }
    }

    crm_config = {
        'service': {
            'id': 'crm-service',
            'base_url': 'https://api.crm-system.com',
            'auth': {
                'id': 'crm-auth',
                'type': 'bearer',
                'token': 'crm-test-token',
            },
            'apis': [
                {
                    'id': 'get-customers',
                    'path': '/customers',
                    'backend_path': '/customers',
                    'method': 'GET',
                }
            ],
        }
    }

    return {
        sample_yaml_config['service']['id']: yaml.dump(sample_yaml_config),
        another_config['service']['id']: yaml.dump(another_config),
        crm_config['service']['id']: yaml.dump(crm_config),
    }


@pytest.fixture
def mock_api_services_manager(sample_service_yaml_map):
    """Mock ApiServicesManager backed by sample YAML definitions."""
    return MockApiServicesManager(service_yaml_map=sample_service_yaml_map.copy())


@pytest.fixture
def mock_cloud_storage_manager():
    """Mock cloud storage manager fixture."""
    return MockCloudStorageManager()


@pytest.fixture
def mock_api_service_repository():
    """Mock API services repository fixture."""
    return MockApiServicesRepository()


# ============================================================================
# Component Fixtures
# ============================================================================


@pytest.fixture
async def service_registry(mock_api_services_manager):
    """Service registry with loaded configurations from mock manager."""
    registry = ServiceRegistry(mock_api_services_manager)
    await registry.load_from_db()
    return registry


@pytest.fixture
def service_parser():
    """Service definition parser."""
    return ServiceDefinitionParser()


@pytest.fixture
def auth_manager():
    """Authentication manager."""
    return AuthManager()


@pytest.fixture
def pipeline_builder():
    """Pipeline builder."""
    return PipelineBuilder()


@pytest.fixture
def pipeline_cache():
    """Pipeline cache."""
    return PipelineCache()


@pytest.fixture
async def api_proxy(service_registry, mock_api_services_manager):
    """API proxy with loaded service registry."""
    return ApiProxy(service_registry, mock_api_services_manager)


@pytest.fixture
async def proxy_router(service_registry, mock_api_services_manager):
    """Proxy router with loaded service registry."""
    return ProxyRouter(service_registry, mock_api_services_manager)


# ============================================================================
# Container Fixtures
# ============================================================================


class MockResponseFormatter:
    def buildSuccessResponse(self, data: Any):
        meta = Meta(status='success', code=1)
        if hasattr(data, 'dict'):
            data = data.dict()
        return ResponseModel(meta=meta, data=data).model_dump()

    def buildErrorResponse(self, error: str):
        meta = Meta(status='failure', code=-1, error=error)
        return ResponseModel(meta=meta).model_dump()


@pytest.fixture
def mock_response_formatter():
    return MockResponseFormatter()


@pytest.fixture
def api_services_container(
    mock_api_service_repository,
    mock_cloud_storage_manager,
    mock_db_client,
    mock_cache_manager,
    mock_api_services_manager,
    mock_response_formatter,
):
    """Configured API services container."""
    container = create_api_services_container(
        api_service_repository=mock_api_service_repository,
        cloud_storage_manager=mock_cloud_storage_manager,
        db_client=mock_db_client,
        cache_manager=mock_cache_manager,
        response_formatter=mock_response_formatter,
    )
    container.api_service_manager.override(providers.Object(mock_api_services_manager))
    container.config.from_dict({'api_service': {'application_bucket': 'test-bucket'}})
    return container


@pytest.fixture
async def initialized_container(api_services_container):
    """API services container with initialized components."""
    # Initialize the service registry
    service_registry = api_services_container.initialized_service_registry()

    # Load services from DB (async operation)
    if service_registry.api_service_manager:
        await service_registry.load_from_db()

        # Reload routes after services are loaded
        proxy_router = api_services_container.proxy_router()
        proxy_router.reload_routes()

    # Wire the container
    api_services_container.wire(modules=[])

    return api_services_container


# ============================================================================
# Pipeline Context Fixtures
# ============================================================================


@pytest.fixture
def sample_pipeline_context():
    """Sample pipeline context for testing."""
    return PipelineContext(
        service_id='test-service',
        api_id='get-users',
        api_version='v1',
        method='POST',
        path='/test/path',
        query_params={'limit': '10', 'offset': '0'},
        headers={'User-Agent': 'test-client', 'Content-Type': 'application/json'},
        body={'test': 'data'},
    )


@pytest.fixture
def authenticated_pipeline_context(sample_pipeline_context):
    """Pipeline context with authentication headers."""
    context = sample_pipeline_context
    context.auth_headers = {'Authorization': 'Bearer test-token'}
    context.backend_headers = {'Authorization': 'Bearer test-token'}
    return context


# ============================================================================
# HTTP Mock Fixtures
# ============================================================================


@pytest.fixture
def mock_httpx_response():
    """Mock httpx response."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {'Content-Type': 'application/json'}
    mock_response.json.return_value = {'success': True, 'data': 'test'}
    mock_response.text = '{"success": true, "data": "test"}'
    mock_response.raise_for_status.return_value = None
    return mock_response


@pytest.fixture
def mock_httpx_client(mock_httpx_response):
    """Mock httpx client."""
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.request.return_value = mock_httpx_response
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None
    return mock_client


# ============================================================================
# FastAPI Test Client Fixtures
# ============================================================================


@pytest.fixture
async def test_client(initialized_container):
    """FastAPI test client for the API services module."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI

    app = FastAPI()
    router = initialized_container.router()
    app.include_router(router)  # No prefix - routes already have /floware/v1

    return TestClient(app)


# ============================================================================
# Async Test Fixtures
# ============================================================================


@pytest.fixture
async def async_api_proxy(service_registry, mock_api_services_manager):
    """Async API proxy fixture."""
    proxy = ApiProxy(service_registry, mock_api_services_manager)
    return proxy


@pytest.fixture
async def async_mock_dependencies():
    """Async mock dependencies."""
    db_client = MockDatabaseClient()
    cache_manager = MockCacheManager()

    await db_client.connect()
    db_client.run_migration()

    return {'db_client': db_client, 'cache_manager': cache_manager}


# ============================================================================
# Utility Fixtures
# ============================================================================


@pytest.fixture
def sample_request_data():
    """Sample request data for testing."""
    return {
        'service_id': 'test-service',
        'api_id': 'get-users',
        'api_version': 'v1',
        'method': 'POST',
        'path': '/test',
        'query_params': {'page': '1'},
        'headers': {'Authorization': 'Bearer test'},
        'body': {'filter': 'active'},
    }


@pytest.fixture
def sample_backend_response():
    """Sample backend response data."""
    return {
        'users': [
            {'id': 1, 'name': 'John', 'email': 'john@test.com'},
            {'id': 2, 'name': 'Jane', 'email': 'jane@test.com'},
        ],
        'total': 2,
        'page': 1,
    }


# ============================================================================
# Cleanup Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Cleanup fixture that runs after each test."""
    yield
    # Cleanup code here if needed
    pass


# ============================================================================
# Parametrized Fixtures
# ============================================================================


@pytest.fixture(params=[AuthType.BEARER, AuthType.BASIC, AuthType.API_KEY])
def auth_type(request):
    """Parametrized auth type fixture."""
    return request.param


@pytest.fixture(
    params=[HttpMethod.GET, HttpMethod.POST, HttpMethod.PUT, HttpMethod.DELETE]
)
def http_method(request):
    """Parametrized HTTP method fixture."""
    return request.param


# ============================================================================
# Configuration Override Fixtures
# ============================================================================


@pytest.fixture
def override_config():
    """Configuration overrides for testing."""
    return {'timeout': 5, 'max_retries': 1, 'log_level': 'DEBUG'}


# ============================================================================
# Error Simulation Fixtures
# ============================================================================


@pytest.fixture
def mock_network_error():
    """Mock network error for testing error handling."""
    import httpx

    return httpx.RequestError('Network error')


@pytest.fixture
def mock_http_error():
    """Mock HTTP error for testing error handling."""
    import httpx

    mock_response = Mock()
    mock_response.status_code = 500
    return httpx.HTTPStatusError('Server error', request=Mock(), response=mock_response)
