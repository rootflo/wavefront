import json
from typing import Any, cast
from unittest.mock import Mock
from uuid import uuid4

from auth_module.auth_container import AuthContainer
from common_module.common_container import CommonContainer
from common_module.middleware.request_id_middleware import RequestIdMiddleware
from db_repo_module.database.base import Base
from db_repo_module.db_repo_container import DatabaseModuleContainer
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
import testing.postgresql
from user_management_module.authorization.require_auth import RequireAuthMiddleware
from user_management_module.user_container import UserContainer
from floware.controllers.config_controller import config_router
from floware.di.application_container import ApplicationContainer
from flo_cloud.cloud_storage import CloudStorageManager
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.config import Config
from floware.services.config_service import ConfigService
from starlette.middleware import _MiddlewareFactory


class MockDbClient:
    def __init__(self, engine, session_factory):
        self._engine = engine
        self.session = session_factory


def _middleware(cls: type[Any]) -> _MiddlewareFactory[Any]:
    return cast(_MiddlewareFactory[Any], cls)


@pytest.fixture
async def test_engine():
    with testing.postgresql.Postgresql() as postgresql:
        database_url = postgresql.url()

        async_database_url = database_url.replace(
            'postgresql://', 'postgresql+psycopg://'
        )

        engine = create_async_engine(async_database_url)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        yield engine

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def test_session(test_engine):
    async_session = async_sessionmaker(autocommit=False, bind=test_engine)
    yield async_session


@pytest.fixture
def test_user_id():
    """Fixture to provide a consistent test user ID."""
    return str(uuid4())


@pytest.fixture
def test_session_id():
    """Fixture to provide a consistent test session ID."""
    return str(uuid4())


@pytest.fixture
def setup_containers(test_engine, test_session, test_user_id, test_session_id):
    db_repo_container = DatabaseModuleContainer()
    mock_db_client = MockDbClient(test_engine, test_session)
    db_repo_container.db_client.override(mock_db_client)
    user_container = UserContainer()

    common_container = CommonContainer()

    cache_manager_mock = Mock()
    # For session data
    cache_manager_mock.get_str.return_value = json.dumps(
        {'user_id': test_user_id, 'device_info': 'Mozilla/5.0'}
    )
    # For reset password
    cache_manager_mock.get_str.side_effect = (
        lambda key: test_user_id
        if key == 'mock_reset_code'
        else json.dumps({'user_id': test_user_id, 'device_info': 'Mozilla/5.0'})
    )
    cache_manager_mock.add = Mock()
    common_container.cache_manager.override(cache_manager_mock)

    user_container.db_client.override(mock_db_client)
    user_container.cache_manager.override(cache_manager_mock)

    # Mock token service
    mock_token_service = Mock()
    mock_token_service.create_token.return_value = 'mock_token'
    mock_token_service.decode_token.return_value = {
        'sub': 'test@example.com',
        'user_id': test_user_id,
        'role_id': 'test_role_id',
        'session_id': test_session_id,
        'code': 'mock_reset_code',
    }
    mock_token_service.token_expiry = 3600
    mock_token_service.temporary_token_expiry = 600

    auth_container = AuthContainer(
        db_client=db_repo_container.db_client,
        cache_manager=cache_manager_mock,
    )
    auth_container.token_service.override(mock_token_service)

    # mocking auth container superset_service
    mock_superset_service = Mock()
    mock_superset_service.generate_guest_token.return_value = 'mock_guest_token'
    auth_container.superset_service.override(mock_superset_service)

    user_container.wire(
        packages=[
            'user_management_module.authorization',
            'user_management_module.utils',
            'auth_module.controllers',
        ]
    )

    common_container.wire(
        packages=[
            'auth_module.controllers',
            'user_management_module.authorization',
            'floware.controllers',
        ]
    )
    auth_container.wire(
        packages=[
            'user_management_module.authorization',
        ]
    )

    yield auth_container, common_container
    auth_container.unwire()
    common_container.unwire()

    db_repo_container.unwire()


@pytest.fixture
def mock_cloud_manager():
    """Mock CloudStorageManager for testing"""
    mock_cloud = Mock(spec=CloudStorageManager)
    mock_cloud.save_small_file = Mock()
    mock_cloud.generate_presigned_url = Mock(
        return_value='https://mock-presigned-url.com/config.png'
    )
    return mock_cloud


@pytest.fixture
def mock_config_repository():
    """Mock config repository for testing"""
    mock_repo = Mock(spec=SQLAlchemyRepository[Config])
    mock_repo.upsert = Mock()
    mock_repo.find = Mock(return_value=[Mock(value={'app_icon': 'config.png'})])
    return mock_repo


@pytest.fixture
def mock_config():
    """Mock configuration for testing"""
    return {
        'gcp': {
            'gcp_asset_storage_bucket': 'test-bucket',
            'config_file_name': 'config.png',
        }
    }


@pytest.fixture
def mock_config_service():
    """Mock config service for testing"""
    mock_service = Mock(spec=ConfigService)

    # Mock async methods
    async def mock_store_app_config(file, app_config_dict):
        return None

    async def mock_get_app_config():
        return 'https://test-bucket.com/config.png', {}

    mock_service.store_app_config = mock_store_app_config
    mock_service.get_app_config = mock_get_app_config

    return mock_service


@pytest.fixture
def setup_application_container(
    mock_cloud_manager, mock_config_repository, mock_config, mock_config_service
):
    """Setup ApplicationContainer with mocked dependencies"""
    app_container = ApplicationContainer()

    # Override the dependencies
    app_container.cloud_manager.override(mock_cloud_manager)
    app_container.config_repository.override(mock_config_repository)
    app_container.config.override(mock_config)
    app_container.config_service.override(mock_config_service)

    # Wire the container
    app_container.wire(modules=[__name__], packages=['floware.controllers'])

    yield app_container

    # Cleanup
    app_container.unwire()


@pytest.fixture
def test_client(setup_containers, setup_application_container):
    app = FastAPI()
    app.add_middleware(_middleware(RequestIdMiddleware))
    app.add_middleware(_middleware(RequireAuthMiddleware))
    app.include_router(config_router, prefix='/floware')
    return TestClient(app)


@pytest.fixture
def mock_auth_functions(monkeypatch):
    async def mock_get_current_user(request):
        return 'test_user_id', 'test_role_id', 'test_session_id'

    async def mock_check_is_admin(role_id):
        return True

    monkeypatch.setattr(
        'user_management_module.controllers.user_controller.get_current_user',
        mock_get_current_user,
    )


@pytest.fixture
def mock_admin_functions(monkeypatch):
    """Mock check_is_admin to return True for admin tests"""

    async def mock_check_is_admin(role_id, role_repository=None):
        return True

    monkeypatch.setattr(
        'floware.controllers.config_controller.check_is_admin',
        mock_check_is_admin,
    )


@pytest.fixture
def mock_non_admin_functions(monkeypatch):
    """Mock check_is_admin to return False for non-admin tests"""

    async def mock_check_is_admin(role_id, role_repository=None):
        return False

    monkeypatch.setattr(
        'floware.controllers.config_controller.check_is_admin',
        mock_check_is_admin,
    )


@pytest.fixture
def auth_token(setup_containers, test_user_id, test_session_id):
    auth_container, _ = setup_containers
    token_service = auth_container.token_service()
    token = token_service.create_token(
        sub='test@example.com',
        user_id=test_user_id,
        role_id='test_role_id',
        session_id=test_session_id,
    )
    return token
