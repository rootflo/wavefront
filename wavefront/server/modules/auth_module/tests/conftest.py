from unittest.mock import Mock
from uuid import uuid4
import os

from auth_module.auth_container import AuthContainer
from auth_module.controllers.superset_controller import superset_controller
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
from db_repo_module.models.datasource import Datasource  # noqa: F401
from db_repo_module.models.dynamic_query_yaml import DynamicQueryYaml  # noqa: F401

# Enable SUPERSET_FLAG for tests
os.environ['SUPERSET_FLAG'] = 'true'


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

    common_container = CommonContainer()
    cache_manager_mock = Mock()

    # Mock token service
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

    auth_container = AuthContainer(
        db_client=db_repo_container.db_client,
        cache_manager=cache_manager_mock,
    )
    auth_container.token_service.override(mock_token_service)

    # mocking auth container superset_service
    mock_superset_service = Mock()
    mock_superset_service.generate_guest_token.return_value = 'mock_guest_token'
    if hasattr(auth_container, 'superset_service'):
        auth_container.superset_service.override(mock_superset_service)

    user_container = UserContainer(
        db_client=db_repo_container.db_client,
        cache_manager=cache_manager_mock,
    )
    # mocking user container cache_manager
    cache_manager_mock = Mock()
    cache_manager_mock.get_str.return_value = None
    user_container.cache_manager.override(cache_manager_mock)

    common_container.wire(
        packages=[
            'user_management_module.controllers',
            'auth_module.controllers',
            'user_management_module.authorization',
        ]
    )
    auth_container.wire(
        packages=[
            'auth_module.controllers',
            'user_management_module.authorization',
        ]
    )
    user_container.wire(
        packages=[
            'user_management_module.authorization',
            'auth_module.controllers',
        ]
    )
    yield auth_container, common_container
    auth_container.unwire()
    common_container.unwire()
    user_container.unwire()


@pytest.fixture
def test_client(setup_containers):
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(RequireAuthMiddleware)
    app.include_router(superset_controller)
    return TestClient(app)


@pytest.fixture
def mock_auth_functions(monkeypatch):
    async def mock_check_is_admin(role_id):
        return True

    monkeypatch.setattr(
        'auth_module.controllers.superset_controller.check_is_admin',
        mock_check_is_admin,
    )


@pytest.fixture
def mock_admin_false_functions(monkeypatch):
    async def mock_check_is_not_admin(role_id):
        return False

    monkeypatch.setattr(
        'auth_module.controllers.superset_controller.check_is_admin',
        mock_check_is_not_admin,
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
