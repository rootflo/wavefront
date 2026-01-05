import json
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
from user_management_module.router import user_management_router
from user_management_module.user_container import UserContainer
from io import BytesIO
from knowledge_base_module.knowledge_base_container import KnowledgeBaseContainer
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
def mock_config():
    """Fixture to provide mock config for testing."""
    return {
        'web': {'url': 'http://test.example.com'},
        'auth': {
            'max_failed_attempts': '3',
            'lockout_duration_hours': '24',
            'inactive_days_threshold': '60',
        },
    }


@pytest.fixture
def setup_containers(
    test_engine, test_session, test_user_id, test_session_id, mock_config
):
    db_repo_container = DatabaseModuleContainer()
    mock_db_client = MockDbClient(test_engine, test_session)
    db_repo_container.db_client.override(mock_db_client)

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

    user_container = UserContainer(
        db_client=db_repo_container.db_client,
        cache_manager=cache_manager_mock,
    )
    user_container.config.override(mock_config)

    # Mock email service
    # Mock email service
    mock_email_service = Mock()
    mock_email_service.send_forget_password_email.return_value = True
    user_container.email_service.override(mock_email_service)

    # Setup KnowledgeBaseContainer for auth_module.controllers (outlook_controller)
    knowledge_base_container = KnowledgeBaseContainer(
        db_client=db_repo_container.db_client,
        cache_manager=cache_manager_mock,
    )

    # Mock CloudStorageManager
    mock_cloud_storage = Mock()
    mock_cloud_storage.save_small_file = Mock()
    mock_cloud_storage.save_large_file = Mock()
    mock_cloud_storage.get_file = Mock(return_value=BytesIO(b'file content'))
    knowledge_base_container.cloud_storage.override(
        providers.Singleton(lambda: mock_cloud_storage)
    )

    # Mock MessageQueueManager
    mock_message_queue = Mock()
    mock_message_queue.add_message = Mock(return_value='message_id_123')
    knowledge_base_container.message_queue.override(
        providers.Singleton(lambda: mock_message_queue)
    )

    # Mock config
    test_kb_config_dict = {
        'cloud_config': {'cloud_provider': 'gcp'},
        'gcp': {
            'gcp_asset_storage_bucket': 'test_bucket',
            'email_topic_id': 'test_topic',
        },
        'aws': {
            'aws_asset_storage_bucket': 'test_bucket',
            'queue_url': 'test_queue_url',
        },
    }
    knowledge_base_container.config.from_dict(test_kb_config_dict)

    # Wire KnowledgeBaseContainer
    knowledge_base_container.wire(
        packages=[
            'auth_module.controllers',
        ]
    )

    mock_email_service.send_forget_password_email.return_value = True
    user_container.email_service.override(mock_email_service)

    common_container.wire(
        packages=[
            'user_management_module.controllers',
            'auth_module.controllers',
            'user_management_module.authorization',
        ]
    )
    auth_container.wire(
        packages=[
            'user_management_module.controllers',
            'user_management_module.authorization',
        ]
    )
    user_container.wire(
        packages=[
            'user_management_module.authorization',
            'user_management_module.controllers',
            'auth_module.controllers',
        ]
    )

    yield auth_container, common_container, user_container
    auth_container.unwire()
    common_container.unwire()


@pytest.fixture
def test_client(setup_containers):
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(RequireAuthMiddleware)
    app.include_router(user_management_router, prefix='/floware')
    return TestClient(app)


@pytest.fixture
def mock_auth_functions(monkeypatch):
    async def mock_get_current_user(request):
        return 'test_user_id', 'test_role_id', 'test_session_id'

    async def mock_check_is_admin(role_id):
        return True

    monkeypatch.setattr(
        'auth_module.controllers.superset_controller.check_is_admin',
        mock_check_is_admin,
    )
    monkeypatch.setattr(
        'user_management_module.utils.user_utils.get_current_user',
        mock_get_current_user,
    )


@pytest.fixture
def mock_auth_admin_functions(monkeypatch):
    def mock_get_current_user(request):
        return 'test_user_id', 'test_role_id', 'test_session_id'

    monkeypatch.setattr(
        'user_management_module.controllers.access_controller.get_current_user',
        mock_get_current_user,
    )

    async def mock_check_is_admin(role_id, role_repository=None):
        return True

    monkeypatch.setattr(
        'user_management_module.controllers.access_controller.check_is_admin',
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
    auth_container, _, _ = setup_containers
    token_service = auth_container.token_service()
    token = token_service.create_token(
        sub='test@example.com',
        user_id=test_user_id,
        role_id='test_role_id',
        session_id=test_session_id,
    )
    return token


@pytest.fixture
def mock_auth_admin_user_functions(monkeypatch, test_user_id):
    def mock_get_current_user(request):
        return (
            'test_role_id',
            test_user_id,
            'test_session_id',
        )  # Use the actual UUID from the fixture

    monkeypatch.setattr(
        'user_management_module.controllers.user_controller.get_current_user',
        mock_get_current_user,
    )

    async def mock_check_is_admin(role_id, role_repository=None):
        return True

    monkeypatch.setattr(
        'user_management_module.controllers.user_controller.check_is_admin',
        mock_check_is_admin,
    )


@pytest.fixture
def mocking_user_controller_is_admin(monkeypatch):
    async def mock_check_is_admin(role_id):
        return True

    monkeypatch.setattr(
        'user_management_module.controllers.user_controller.check_is_admin',
        mock_check_is_admin,
    )


@pytest.fixture
def mocking_user_controller_get_current_user(monkeypatch, test_user_id):
    def mock_get_current_user(request):
        return 'wrong_role_id', test_user_id, 'test_session_id'

    monkeypatch.setattr(
        'user_management_module.controllers.user_controller.get_current_user',
        mock_get_current_user,
    )
