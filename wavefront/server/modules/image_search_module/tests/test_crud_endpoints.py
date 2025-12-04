"""
Comprehensive CRUD endpoint tests for Image Search Module
Tests all endpoints: Create, Read, Update, Delete operations
"""

import pytest
import base64
from unittest.mock import Mock, AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from datetime import datetime
from uuid import uuid4

from image_search_module.controllers.image_search_controller import image_search_router
from image_search_module.image_search_container import ImageSearchContainer
from image_search_module.algorithms.base import AlgorithmType
from image_search_module.models.ikb_models import (
    IKBType,
    IKBStatus,
)
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


# Create a custom mock IKBInfo that serializes properly
class MockIKBInfo:
    """Mock IKBInfo that serializes enums properly"""

    def __init__(self, **kwargs):
        self.ikb_id = kwargs.get('ikb_id', str(uuid4()))
        self.name = kwargs.get('name', 'Test IKB')
        self.description = kwargs.get('description', 'Test IKB for unit testing')
        self.ikb_type = kwargs.get('ikb_type', IKBType.GOLD_MATCHING)
        self.algorithm_type = kwargs.get('algorithm_type', AlgorithmType.SIFT)
        self.status = kwargs.get('status', IKBStatus.ACTIVE)
        self.image_count = kwargs.get('image_count', 0)
        self.created_at = kwargs.get('created_at', datetime.now())
        self.updated_at = kwargs.get('updated_at', datetime.now())
        self.config = kwargs.get('config', {'threshold': 0.8})

    def dict(self):
        """Return dictionary with enum values serialized as strings"""
        return {
            'ikb_id': self.ikb_id,
            'name': self.name,
            'description': self.description,
            'ikb_type': self.ikb_type.value
            if hasattr(self.ikb_type, 'value')
            else str(self.ikb_type),
            'algorithm_type': self.algorithm_type.value
            if hasattr(self.algorithm_type, 'value')
            else str(self.algorithm_type),
            'status': self.status.value
            if hasattr(self.status, 'value')
            else str(self.status),
            'image_count': self.image_count,
            'created_at': self.created_at.isoformat()
            if isinstance(self.created_at, datetime)
            else self.created_at,
            'updated_at': self.updated_at.isoformat()
            if isinstance(self.updated_at, datetime)
            else self.updated_at,
            'config': self.config,
        }

    def model_dump(self, mode='json'):
        """Pydantic v2 compatibility - calls dict() method"""
        return self.dict()


# Create a custom mock IKBSearchResponse that serializes properly
class MockIKBSearchResponse:
    """Mock IKBSearchResponse that serializes properly"""

    def __init__(self, **kwargs):
        self.query_id = kwargs.get('query_id', str(uuid4()))
        self.ikb_id = kwargs.get('ikb_id', str(uuid4()))
        self.ikb_name = kwargs.get('ikb_name', 'Test IKB')
        self.algorithm_used = kwargs.get('algorithm_used', 'sift')
        self.matches = kwargs.get('matches', [])
        self.total_images_searched = kwargs.get('total_images_searched', 0)
        self.processing_time_ms = kwargs.get('processing_time_ms', 0.0)

    def dict(self):
        """Return dictionary representation"""
        return {
            'query_id': self.query_id,
            'ikb_id': self.ikb_id,
            'ikb_name': self.ikb_name,
            'algorithm_used': self.algorithm_used,
            'matches': self.matches,
            'total_images_searched': self.total_images_searched,
            'processing_time_ms': self.processing_time_ms,
        }


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
    mock_reference_features_repository = Mock()
    mock_sift_features_repository = Mock()

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


@pytest.fixture
def sample_image_data():
    """Create a sample base64 image data URL for testing"""
    # Create a minimal 1x1 pixel PNG in base64
    # This is a valid but minimal PNG file
    png_data = base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
    )
    return f'data:image/png;base64,{base64.b64encode(png_data).decode()}'


@pytest.fixture
def sample_ikb_data():
    """Sample IKB data for testing"""
    return {
        'name': 'Test IKB',
        'description': 'Test IKB for unit testing',
        'ikb_type': 'gold_matching',
        'algorithm_type': 'sift',
        'config': {'threshold': 0.8},
    }


@pytest.fixture
def mock_ikb_info():
    """Mock IKB info object that serializes properly"""
    return MockIKBInfo(
        ikb_id=str(uuid4()),
        name='Test IKB',
        description='Test IKB for unit testing',
        ikb_type=IKBType.GOLD_MATCHING,
        algorithm_type=AlgorithmType.SIFT,
        status=IKBStatus.ACTIVE,
        image_count=0,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        config={'threshold': 0.8},
    )


class TestIKBCreateEndpoint:
    """Test CREATE operations"""

    def test_create_ikb_success(
        self, test_client, sample_ikb_data, mock_containers, mock_ikb_info
    ):
        """Test successful IKB creation"""
        db_repo_container, common_container, image_search_container = mock_containers

        # Mock the IKB service to return our mock IKB info
        mock_ikb_service = Mock()
        mock_ikb_service.create_ikb = AsyncMock(return_value=mock_ikb_info)
        image_search_container.ikb_service.override(mock_ikb_service)

        response = test_client.post('/floware/ikb/create', json=sample_ikb_data)

        assert response.status_code == 201
        response_data = response.json()
        assert response_data['meta']['status'] == 'success'
        assert response_data['data']['name'] == sample_ikb_data['name']
        assert response_data['data']['ikb_type'] == sample_ikb_data['ikb_type']
        assert (
            response_data['data']['algorithm_type'] == sample_ikb_data['algorithm_type']
        )

    def test_create_ikb_invalid_data(self, test_client):
        """Test IKB creation with invalid data"""
        invalid_data = {
            'name': '',  # Empty name should fail validation
            'ikb_type': 'invalid_type',
            'algorithm_type': 'invalid_algorithm',
        }

        response = test_client.post('/floware/ikb/create', json=invalid_data)
        assert response.status_code == 422  # Validation error

    def test_create_ikb_missing_required_fields(self, test_client):
        """Test IKB creation with missing required fields"""
        incomplete_data = {
            'name': 'Test IKB'
            # Missing ikb_type and algorithm_type
        }

        response = test_client.post('/floware/ikb/create', json=incomplete_data)
        assert response.status_code == 422  # Validation error


class TestIKBReadEndpoints:
    """Test READ operations"""

    def test_list_ikbs_success(self, test_client, mock_containers, mock_ikb_info):
        """Test successful IKB listing"""
        db_repo_container, common_container, image_search_container = mock_containers

        # Mock the IKB service to return a list of IKBs
        mock_ikb_service = Mock()
        mock_ikb_service.list_ikbs = AsyncMock(return_value=[mock_ikb_info])
        image_search_container.ikb_service.override(mock_ikb_service)

        response = test_client.get('/floware/ikb/')

        assert response.status_code == 200
        response_data = response.json()
        assert response_data['meta']['status'] == 'success'
        assert 'ikbs' in response_data['data']
        assert len(response_data['data']['ikbs']) == 1
        assert response_data['data']['ikbs'][0]['name'] == mock_ikb_info.name

    def test_list_ikbs_with_type_filter(
        self, test_client, mock_containers, mock_ikb_info
    ):
        """Test IKB listing with type filter"""
        db_repo_container, common_container, image_search_container = mock_containers

        # Mock the IKB service
        mock_ikb_service = Mock()
        mock_ikb_service.list_ikbs = AsyncMock(return_value=[mock_ikb_info])
        image_search_container.ikb_service.override(mock_ikb_service)

        response = test_client.get('/floware/ikb/?ikb_type=gold_matching')

        assert response.status_code == 200
        # Verify that the service was called with the correct filter
        mock_ikb_service.list_ikbs.assert_called_once_with(
            ikb_type=IKBType.GOLD_MATCHING
        )

    def test_list_ikbs_empty(self, test_client, mock_containers):
        """Test IKB listing when no IKBs exist"""
        db_repo_container, common_container, image_search_container = mock_containers

        # Mock the IKB service to return empty list
        mock_ikb_service = Mock()
        mock_ikb_service.list_ikbs = AsyncMock(return_value=[])
        image_search_container.ikb_service.override(mock_ikb_service)

        response = test_client.get('/floware/ikb/')

        assert response.status_code == 200
        response_data = response.json()
        assert response_data['meta']['status'] == 'success'
        assert response_data['data']['ikbs'] == []

    def test_get_ikb_success(self, test_client, mock_containers, mock_ikb_info):
        """Test successful IKB retrieval by ID"""
        db_repo_container, common_container, image_search_container = mock_containers

        # Mock the IKB service
        mock_ikb_service = Mock()
        mock_ikb_service.get_ikb = AsyncMock(return_value=mock_ikb_info)
        image_search_container.ikb_service.override(mock_ikb_service)

        response = test_client.get(f'/floware/ikb/{mock_ikb_info.ikb_id}')

        assert response.status_code == 200
        response_data = response.json()
        assert response_data['meta']['status'] == 'success'
        assert response_data['data']['ikb_id'] == mock_ikb_info.ikb_id
        assert response_data['data']['name'] == mock_ikb_info.name

    def test_get_ikb_not_found(self, test_client, mock_containers):
        """Test IKB retrieval when IKB doesn't exist"""
        db_repo_container, common_container, image_search_container = mock_containers

        # Mock the IKB service to return None (not found)
        mock_ikb_service = Mock()
        mock_ikb_service.get_ikb = AsyncMock(return_value=None)
        image_search_container.ikb_service.override(mock_ikb_service)

        fake_id = str(uuid4())
        response = test_client.get(f'/floware/ikb/{fake_id}')

        assert response.status_code == 404
        response_data = response.json()
        assert response_data['meta']['status'] == 'failure'
        assert f'IKB with ID {fake_id} not found' in response_data['meta']['error']


class TestIKBUpdateOperations:
    """Test UPDATE operations (adding images to IKB)"""

    def test_add_image_to_ikb_success(
        self, test_client, mock_containers, sample_image_data, mock_ikb_info
    ):
        """Test successful image addition to IKB"""
        db_repo_container, common_container, image_search_container = mock_containers

        # Mock the IKB service
        mock_ikb_service = Mock()
        mock_result = {
            'status': 'success',
            'reference_id': str(uuid4()),
            'message': 'Image added successfully',
        }
        mock_ikb_service.add_image_to_ikb = AsyncMock(return_value=mock_result)
        image_search_container.ikb_service.override(mock_ikb_service)

        payload = {
            'image_data': sample_image_data,
            'reference_id': 'test_ref_123',
            'metadata': {'source': 'test'},
        }

        response = test_client.post(
            f'/floware/ikb/{mock_ikb_info.ikb_id}/add', json=payload
        )

        assert response.status_code == 201
        response_data = response.json()
        assert response_data['meta']['status'] == 'success'
        assert response_data['data']['status'] == 'success'

    def test_add_image_to_ikb_invalid_image_data(self, test_client, mock_ikb_info):
        """Test image addition with invalid image data"""
        invalid_payload = {
            'image_data': 'invalid_base64_data',  # Invalid format
            'reference_id': 'test_ref_123',
        }

        response = test_client.post(
            f'/floware/ikb/{mock_ikb_info.ikb_id}/add', json=invalid_payload
        )
        assert response.status_code == 422  # Validation error

    def test_search_in_ikb_success(
        self, test_client, mock_containers, sample_image_data, mock_ikb_info
    ):
        """Test successful image search in IKB"""
        db_repo_container, common_container, image_search_container = mock_containers

        # Mock the IKB service
        mock_ikb_service = Mock()
        mock_search_response = MockIKBSearchResponse(
            query_id=str(uuid4()),
            ikb_id=mock_ikb_info.ikb_id,
            ikb_name=mock_ikb_info.name,
            algorithm_used='sift',
            matches=[
                {
                    'reference_id': 'ref_1',
                    'match_score': 0.95,
                    'confidence': 0.9,
                    'metadata': {},
                }
            ],
            total_images_searched=10,
            processing_time_ms=150.5,
        )
        mock_ikb_service.search_in_ikb = AsyncMock(return_value=mock_search_response)
        image_search_container.ikb_service.override(mock_ikb_service)

        payload = {
            'ikb_id': mock_ikb_info.ikb_id,
            'image_data': sample_image_data,
            'max_results': 5,
            'threshold': 0.8,
        }

        response = test_client.post(
            f'/floware/ikb/{mock_ikb_info.ikb_id}/search', json=payload
        )

        assert response.status_code == 200
        response_data = response.json()
        assert response_data['meta']['status'] == 'success'
        assert response_data['data']['ikb_id'] == mock_ikb_info.ikb_id
        assert response_data['data']['algorithm_used'] == 'sift'
        assert len(response_data['data']['matches']) == 1

    def test_search_in_ikb_invalid_image_data(self, test_client, mock_ikb_info):
        """Test image search with invalid image data"""
        invalid_payload = {
            'ikb_id': mock_ikb_info.ikb_id,
            'image_data': 'invalid_base64_data',  # Invalid format
            'max_results': 5,
        }

        response = test_client.post(
            f'/floware/ikb/{mock_ikb_info.ikb_id}/search', json=invalid_payload
        )
        assert response.status_code == 422  # Validation error

    def test_search_in_ikb_invalid_max_results(
        self, test_client, sample_image_data, mock_ikb_info
    ):
        """Test image search with invalid max_results parameter"""
        invalid_payload = {
            'ikb_id': mock_ikb_info.ikb_id,
            'image_data': sample_image_data,
            'max_results': 150,  # Exceeds maximum of 100
        }

        response = test_client.post(
            f'/floware/ikb/{mock_ikb_info.ikb_id}/search', json=invalid_payload
        )
        assert response.status_code == 422  # Validation error


class TestIKBDeleteEndpoint:
    """Test DELETE operations"""

    def test_delete_ikb_success(self, test_client, mock_containers, mock_ikb_info):
        """Test successful IKB deletion"""
        db_repo_container, common_container, image_search_container = mock_containers

        # Mock the IKB service
        mock_ikb_service = Mock()
        mock_ikb_service.delete_ikb = AsyncMock(return_value=True)
        image_search_container.ikb_service.override(mock_ikb_service)

        response = test_client.delete(f'/floware/ikb/{mock_ikb_info.ikb_id}')

        assert response.status_code == 200
        response_data = response.json()
        assert response_data['meta']['status'] == 'success'
        assert 'deleted successfully' in response_data['data']['message']

    def test_delete_ikb_not_found(self, test_client, mock_containers):
        """Test IKB deletion when IKB doesn't exist"""
        db_repo_container, common_container, image_search_container = mock_containers

        # Mock the IKB service to return False (not found)
        mock_ikb_service = Mock()
        mock_ikb_service.delete_ikb = AsyncMock(return_value=False)
        image_search_container.ikb_service.override(mock_ikb_service)

        fake_id = str(uuid4())
        response = test_client.delete(f'/floware/ikb/{fake_id}')

        assert response.status_code == 404
        response_data = response.json()
        assert response_data['meta']['status'] == 'failure'
        assert f'IKB with ID {fake_id} not found' in response_data['meta']['error']


class TestEndpointIntegration:
    """Integration tests for complete workflows"""

    def test_complete_ikb_lifecycle(
        self, test_client, mock_containers, sample_ikb_data, sample_image_data
    ):
        """Test complete IKB lifecycle: create -> add image -> search -> delete"""
        db_repo_container, common_container, image_search_container = mock_containers

        # Create a mock IKB info that serializes properly
        mock_ikb_info = MockIKBInfo(
            ikb_id=str(uuid4()),
            name=sample_ikb_data['name'],
            description=sample_ikb_data['description'],
            ikb_type=IKBType.GOLD_MATCHING,
            algorithm_type=AlgorithmType.SIFT,
            status=IKBStatus.ACTIVE,
            image_count=0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            config=sample_ikb_data['config'],
        )

        # Mock the IKB service for all operations
        mock_ikb_service = Mock()
        mock_ikb_service.create_ikb = AsyncMock(return_value=mock_ikb_info)
        mock_ikb_service.add_image_to_ikb = AsyncMock(
            return_value={'status': 'success', 'reference_id': 'ref_123'}
        )
        mock_ikb_service.search_in_ikb = AsyncMock(
            return_value=MockIKBSearchResponse(
                query_id=str(uuid4()),
                ikb_id=mock_ikb_info.ikb_id,
                ikb_name=mock_ikb_info.name,
                algorithm_used='sift',
                matches=[],
                total_images_searched=1,
                processing_time_ms=100.0,
            )
        )
        mock_ikb_service.delete_ikb = AsyncMock(return_value=True)

        image_search_container.ikb_service.override(mock_ikb_service)

        # 1. Create IKB
        create_response = test_client.post('/floware/ikb/create', json=sample_ikb_data)
        assert create_response.status_code == 201
        created_ikb = create_response.json()['data']
        ikb_id = created_ikb['ikb_id']

        # 2. Add image to IKB
        add_payload = {
            'ikb_id': ikb_id,
            'image_data': sample_image_data,
            'reference_id': 'test_ref_123',
        }
        add_response = test_client.post(f'/floware/ikb/{ikb_id}/add', json=add_payload)
        assert add_response.status_code == 201

        # 3. Search in IKB
        search_payload = {
            'ikb_id': ikb_id,
            'image_data': sample_image_data,
            'max_results': 5,
        }
        search_response = test_client.post(
            f'/floware/ikb/{ikb_id}/search', json=search_payload
        )
        assert search_response.status_code == 200

        # 4. Delete IKB
        delete_response = test_client.delete(f'/floware/ikb/{ikb_id}')
        assert delete_response.status_code == 200

    def test_error_handling_consistency(self, test_client, mock_containers):
        """Test that error responses are consistent across endpoints"""
        db_repo_container, common_container, image_search_container = mock_containers

        # Mock service to raise an exception
        mock_ikb_service = Mock()
        mock_ikb_service.get_ikb = AsyncMock(side_effect=Exception('Database error'))
        image_search_container.ikb_service.override(mock_ikb_service)

        fake_id = str(uuid4())

        # Since the controller doesn't handle exceptions, this will result in a 500 error
        # We need to catch the exception that will be raised by the test client
        with pytest.raises(Exception) as exc_info:
            test_client.get(f'/floware/ikb/{fake_id}')

        # Verify that the exception contains our expected error message
        assert 'Database error' in str(exc_info.value)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
