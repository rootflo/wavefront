import json
from unittest.mock import Mock
from uuid import uuid4

from auth_module.auth_container import AuthContainer
from common_module.common_container import CommonContainer
from common_module.middleware.request_id_middleware import RequestIdMiddleware
from db_repo_module.database.base import Base
from db_repo_module.db_repo_container import DatabaseModuleContainer
from dependency_injector import providers
from fastapi import FastAPI
from fastapi.testclient import TestClient
from insights_module.controllers.pdo_controller import pdo_router
from insights_module.insights_container import InsightsContainer
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
import testing.postgresql
from user_management_module.authorization.require_auth import RequireAuthMiddleware
from user_management_module.user_container import UserContainer


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
    # setting up the dependencies for the requireauth middleware
    auth_container = AuthContainer()
    common_container = CommonContainer()
    user_container = UserContainer()

    db_repo_container = DatabaseModuleContainer()
    mock_db_client = MockDbClient(test_engine, test_session)
    db_repo_container.db_client.override(mock_db_client)

    # mocking the cache manager
    cache_manager_mock = Mock()
    cache_manager_mock.get_str.return_value = json.dumps(
        {'user_id': test_user_id, 'session_id': test_session_id}
    )
    cache_manager_mock.add = Mock()
    common_container.cache_manager.override(cache_manager_mock)

    common_container.cache_manager.override(db_repo_container.cache_manager)
    insights_container = InsightsContainer(
        notification_repository=db_repo_container.notification_repository,
    )

    # Mock connector for PVORepository
    mock_connector = Mock()
    mock_connector.execute_query.return_value = ([], [])
    insights_container.connector.override(providers.Singleton(lambda: mock_connector))

    # Mock cloud service
    mock_cloud_service = Mock()
    mock_cloud_service.fetch_audio.return_value = (
        'https://example.com/audio/test_audio.mp3'
    )
    mock_cloud_service.fetch_upto_limit.return_value = [
        {
            'id': 'test_id_1',
            'conversation_id': 'conv_1',
            'created_at': '2024-03-20T10:00:00',
            'rf_transcription_status': 'success',
            'rf_insights_status': 'success',
            'total_duration': 300,
        },
        {
            'id': 'test_id_2',
            'conversation_id': 'conv_2',
            'created_at': '2024-03-20T11:00:00',
            'rf_transcription_status': 'success',
            'rf_insights_status': 'success',
            'total_duration': 450,
        },
    ]
    mock_cloud_service.fetch_transcript.return_value = {
        'transcript': 'This is a test transcript',
        'metadata': {'duration': 300, 'speaker_count': 2},
    }

    insights_container.cloud_service.override(
        providers.Singleton(lambda: mock_cloud_service)
    )

    # mocking the token service
    mock_token_service = Mock()
    mock_token_service.create_token.return_value = 'mock_token'
    mock_token_service.decode_token.return_value = {
        'sub': 'test@example.com',
        'user_id': test_user_id,
        'role_id': 'test_role_id',
        'session_id': test_session_id,
    }
    mock_token_service.token_expiry = 3600
    mock_token_service.temporary_token_expiry = 600

    # overriding the auth container dependencies
    auth_container.token_service.override(mock_token_service)
    auth_container.db_client.override(db_repo_container.db_client)
    auth_container.cache_manager.override(cache_manager_mock)

    # overriding the user container dependencies
    user_container.db_client.override(db_repo_container.db_client)
    user_container.cache_manager.override(cache_manager_mock)

    auth_container.wire(
        packages=[
            'insights_module.controllers',
            'user_management_module.authorization',
        ]
    )

    user_container.wire(
        packages=[
            'user_management_module.authorization',
            'auth_module.controllers',
            'insights_module.controllers',
        ]
    )
    common_container.wire(
        packages=[
            'insights_module.controllers',
            'user_management_module.authorization',
        ]
    )
    insights_container.wire(
        packages=[
            'insights_module.controllers',
        ]
    )

    yield auth_container, common_container, user_container, insights_container
    auth_container.unwire()
    common_container.unwire()
    user_container.unwire()


@pytest.fixture
def test_client(setup_containers):
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(RequireAuthMiddleware)
    app.include_router(pdo_router, prefix='/floware/v1/insights')
    return TestClient(app)


@pytest.fixture
def auth_token(setup_containers, test_user_id, test_session_id):
    auth_container, _, _, _ = setup_containers
    token_service = auth_container.token_service()
    token = token_service.create_token(
        sub='test@example.com',
        user_id=test_user_id,
        role_id='test_role_id',
        session_id=test_session_id,
    )
    return token


@pytest.fixture
def mocking_pdo_controller_is_admin(monkeypatch):
    async def mock_check_admin(role_id):
        return True

    monkeypatch.setattr(
        'insights_module.controllers.pdo_controller.check_admin',
        mock_check_admin,
    )


@pytest.fixture
def mocking_pdo_controller_not_admin(monkeypatch):
    async def mock_check_admin(role_id):
        return False

    monkeypatch.setattr(
        'insights_module.controllers.pdo_controller.check_admin',
        mock_check_admin,
    )


@pytest.fixture
def mock_pvo_repository_emptydata(setup_containers):
    _, _, _, insights_container = setup_containers
    mock_cloud_service = Mock()
    mock_cloud_service.fetch_audio.return_value = (
        'https://example.com/audio/test_audio.mp3'
    )
    mock_cloud_service.fetch_upto_limit.return_value = []

    # Configure the mock to return the dictionary directly using AsyncMock
    mock_cloud_service.fetch_transcript = Mock(return_value={})
    insights_container.cloud_service.override(
        providers.Singleton(lambda: mock_cloud_service)
    )
