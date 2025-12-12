import json
from unittest.mock import Mock, AsyncMock
from uuid import uuid4

from auth_module.auth_container import AuthContainer
from common_module.common_container import CommonContainer
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
from inference_module.controllers.inference_controller import inference_router
from inference_module.inference_container import InferenceContainer
from dependency_injector import providers


class MockDbClient:
    def __init__(self, engine, session_factory):
        self._engine = engine
        self.session = session_factory


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

    user_container.db_client.override(db_repo_container.db_client)
    user_container.cache_manager.override(cache_manager_mock)
    common_container.cache_manager.override(cache_manager_mock)

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

    inference_container = InferenceContainer(
        db_client=db_repo_container.db_client,
        cache_manager=user_container.cache_manager,
    )

    # Explicitly mock CloudStorageManager with a string provider
    mock_cloud_storage_manager_instance = Mock()
    mock_cloud_storage_manager_instance.save_large_file = AsyncMock(return_value=None)

    inference_container.cloud_storage_manager.override(
        providers.Singleton(lambda: mock_cloud_storage_manager_instance)
    )

    inference_container.wire(packages=['inference_module.controllers'])
    common_container.wire(
        packages=['auth_module.controllers', 'inference_module.controllers']
    )
    auth_container.wire(
        packages=[
            'user_management_module.authorization',
        ]
    )
    user_container.wire(
        packages=[
            'user_management_module.authorization',
        ]
    )

    # Mock config_service
    mock_config_service = Mock()
    mock_config_service.config = {
        'cloud_config': {'cloud_provider': 'gcp'},
        'gcp': {'model_storage_bucket': 'test_bucket'},
        'aws': {'model_storage_bucket': 'test_bucket'},
    }
    inference_container.config.override(
        providers.Singleton(lambda: mock_config_service.config)
    )

    yield auth_container, common_container, inference_container
    auth_container.unwire()
    common_container.unwire()
    inference_container.unwire()


@pytest.fixture
def test_client(setup_containers):
    app = FastAPI()
    app.add_middleware(RequireAuthMiddleware)
    app.include_router(inference_router, prefix='/floware')
    return TestClient(app)


@pytest.fixture
def auth_token(setup_containers, test_user_id, test_session_id):
    auth_container, _, _ = setup_containers
    token_service = auth_container.token_service()
    token = token_service.create_token(
        sub='test@example.com',
        user_id=test_user_id,
        role_id='test_role_id',
        session_id=test_session_id,
    )
    return token
