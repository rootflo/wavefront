"""
Simple test to verify image search module wiring without complex dependencies
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from image_search_module.controllers.image_search_controller import image_search_router
from image_search_module.image_search_container import ImageSearchContainer
from image_search_module.algorithms.base import AlgorithmType
from common_module.common_container import CommonContainer
from db_repo_module.db_repo_container import DatabaseModuleContainer


class MockDbClient:
    def __init__(self):
        # Create a mock session factory
        self.session = MagicMock()
        # Mock the async context manager behavior
        mock_session = MagicMock()
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session.query = Mock()
        mock_session.get = AsyncMock()

        self.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        self.session.return_value.__aexit__ = AsyncMock(return_value=None)


@pytest.fixture
def mock_containers():
    """Setup mock containers for testing"""
    # Mock database container
    db_repo_container = DatabaseModuleContainer()
    mock_db_client = MockDbClient()
    db_repo_container.db_client.override(mock_db_client)

    # Mock common container
    common_container = CommonContainer()
    mock_cache_manager = Mock()
    mock_cache_manager.get_str.return_value = (
        '{"user_id": "test_user", "session_id": "test_session"}'
    )
    mock_cache_manager.add = Mock()
    common_container.cache_manager.override(mock_cache_manager)

    # Mock image search container
    mock_cloud_storage_manager = Mock()
    mock_cloud_storage_manager.save_file = AsyncMock(
        return_value='mock://storage/test.jpg'
    )
    mock_cloud_storage_manager.get_file = AsyncMock(return_value=b'mock_data')

    image_search_container = ImageSearchContainer(
        db_client=mock_db_client,
        cloud_storage_manager=mock_cloud_storage_manager,
    )

    # Override the problematic providers directly
    image_search_container.active_algorithm_type.override(AlgorithmType.SIFT)

    # Mock the repositories with proper async methods and correct return types
    mock_ikb_repository = Mock()
    # Return empty dict instead of empty list for list_ikbs
    mock_ikb_repository.list_ikbs = AsyncMock(return_value=[])
    mock_ikb_repository.get_ikb = AsyncMock(return_value=None)
    mock_ikb_repository.create_ikb = AsyncMock(return_value=Mock())
    mock_ikb_repository.delete_ikb = AsyncMock(return_value=True)

    mock_reference_features_repository = Mock()
    mock_reference_features_repository.create = AsyncMock(return_value=Mock())
    mock_reference_features_repository.get = AsyncMock(return_value=None)

    mock_sift_features_repository = Mock()
    mock_sift_features_repository.create = AsyncMock(return_value=Mock())
    mock_sift_features_repository.get = AsyncMock(return_value=None)

    # Override the repository providers
    image_search_container.ikb_repository.override(mock_ikb_repository)
    image_search_container.reference_features_repository.override(
        mock_reference_features_repository
    )
    image_search_container.sift_features_repository.override(
        mock_sift_features_repository
    )

    # Mock the services that depend on config
    mock_algorithm_factory = Mock()
    mock_algorithm_service = Mock()
    mock_reference_image_service = Mock()
    mock_reference_image_service.add_image_to_ikb = AsyncMock(
        return_value={'status': 'success'}
    )
    mock_reference_image_service.search_in_ikb = AsyncMock(return_value=Mock())

    mock_image_matching_service = Mock()

    image_search_container.algorithm_factory.override(mock_algorithm_factory)
    image_search_container.algorithm_service.override(mock_algorithm_service)
    image_search_container.reference_image_service.override(
        mock_reference_image_service
    )
    image_search_container.image_matching_service.override(mock_image_matching_service)

    # Wire containers
    common_container.wire(packages=['image_search_module.controllers'])
    image_search_container.wire(packages=['image_search_module.controllers'])

    yield db_repo_container, common_container, image_search_container

    # Cleanup
    common_container.unwire()
    image_search_container.unwire()


@pytest.fixture
def test_app(mock_containers):
    """Create test FastAPI app"""
    app = FastAPI()
    app.include_router(image_search_router, prefix='/floware')
    return app


@pytest.fixture
def test_client(test_app):
    """Create test client"""
    return TestClient(test_app)


def test_app_creation(test_app):
    """Test that the FastAPI app can be created with the router"""
    assert test_app is not None
    # Check that routes are registered
    routes = [route.path for route in test_app.routes]
    assert '/floware/ikb/' in routes
    assert '/floware/ikb/create' in routes


def test_router_inclusion(test_app):
    """Test that the image search router is properly included"""
    # Check that the router is included
    assert len(test_app.routes) > 0

    # Check for specific routes
    route_paths = [route.path for route in test_app.routes if hasattr(route, 'path')]
    expected_paths = [
        '/floware/ikb/',
        '/floware/ikb/create',
        '/floware/ikb/{ikb_id}',
        '/floware/ikb/{ikb_id}/add',
        '/floware/ikb/{ikb_id}/search',
    ]

    for expected_path in expected_paths:
        assert any(
            expected_path in path for path in route_paths
        ), f'Route {expected_path} not found'


def test_container_wiring(mock_containers):
    """Test that containers can be wired without errors"""
    db_repo_container, common_container, image_search_container = mock_containers

    # Test that containers are properly set up
    assert db_repo_container is not None
    assert common_container is not None
    assert image_search_container is not None

    # Test that services can be accessed
    try:
        ikb_service = image_search_container.ikb_service()
        assert ikb_service is not None
        print('✅ IKB service created successfully')
    except Exception as e:
        pytest.fail(f'Failed to get ikb_service: {e}')


def test_basic_endpoint_access(test_client):
    """Test that endpoints are accessible (even if they return errors)"""
    # Test GET /floware/ikb/ - should return some response (not 404)
    response = test_client.get('/floware/ikb/')
    print(f'GET /floware/ikb/ status: {response.status_code}')
    # Should not be 404 (route not found)
    assert response.status_code != 404, 'Route not found - wiring issue'

    # Test POST /floware/ikb/create - should return some response (not 404)
    response = test_client.post('/floware/ikb/create', json={})
    print(f'POST /floware/ikb/create status: {response.status_code}')
    # Should not be 404 (route not found)
    assert response.status_code != 404, 'Route not found - wiring issue'


def test_invalid_endpoint_returns_404(test_client):
    """Test that invalid endpoints return 404"""
    response = test_client.get('/floware/invalid-endpoint')
    assert response.status_code == 404


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
