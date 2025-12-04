import json
from unittest.mock import Mock
from io import BytesIO
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
from dependency_injector import providers
import testing.postgresql
from user_management_module.authorization.require_auth import RequireAuthMiddleware
from user_management_module.user_container import UserContainer
from knowledge_base_module.knowledge_base_container import KnowledgeBaseContainer
from knowledge_base_module.controllers.knowledge_base_controller import (
    knowledge_base_router,
)
from knowledge_base_module.controllers.knowledge_base_document_controller import (
    kb_document_router,
)
from knowledge_base_module.controllers.rag_retreival_controller import (
    rag_retrieval_router,
)
from llm_inference_config_module.container import LlmInferenceConfigContainer
from db_repo_module.models.datasource import Datasource  # noqa: F401
from db_repo_module.models.dynamic_query_yaml import DynamicQueryYaml  # noqa: F401
from unittest.mock import AsyncMock


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

    # Initialize LLM Inference Config Container
    llm_inference_config_container = LlmInferenceConfigContainer(
        db_client=db_repo_container.db_client,
        cache_manager=db_repo_container.cache_manager,
    )
    # Override with mock cache manager to avoid Redis connection
    llm_inference_config_container.cache_manager.override(cache_manager_mock)

    knowledge_base_container = KnowledgeBaseContainer(
        db_client=db_repo_container.db_client,
        cache_manager=db_repo_container.cache_manager,
    )
    mock_cloud_storage_manager_instance = Mock()
    mock_cloud_storage_manager_instance.file_protocol = Mock(return_value='gs')

    knowledge_base_container.cloud_storage_manager.override(
        providers.Singleton(lambda: mock_cloud_storage_manager_instance)
    )
    mock_config_service = Mock()
    mock_config_service.config = {
        'cloud_config': {'cloud_provider': 'gcp'},
        'gcp': {'gcp_asset_storage_bucket': 'test_bucket'},
        'aws': {'aws_asset_storage_bucket': 'test_bucket'},
        'model': {'inference_service_url': 'http://mock-inference-url.com'},
    }
    knowledge_base_container.config.override(
        providers.Singleton(lambda: mock_config_service.config)
    )

    auth_container.wire(
        packages=[
            'user_management_module.authorization',
        ]
    )

    user_container.wire(
        packages=[
            'user_management_module.authorization',
            # 'auth_module.controllers',
        ]
    )
    common_container.wire(
        packages=[
            'user_management_module.authorization',
            'knowledge_base_module.controllers',
        ]
    )
    knowledge_base_container.wire(
        packages=[
            'knowledge_base_module.controllers',
        ],
    )
    llm_inference_config_container.wire(
        packages=[
            'knowledge_base_module.controllers',
        ],
    )

    # Mock CloudStorageManager for kb_document_router
    mock_cloud_storage = Mock()
    mock_cloud_storage.save_small_file = Mock()
    mock_cloud_storage.save_large_file = Mock()
    mock_cloud_storage.get_file = Mock(return_value=BytesIO(b'file content'))
    knowledge_base_container.cloud_storage.override(
        providers.Singleton(lambda: mock_cloud_storage)
    )

    # Mock MessageQueueManager for kb_document_router
    mock_message_queue = Mock()
    mock_message_queue.add_message = Mock(return_value='message_id_123')
    knowledge_base_container.message_queue.override(
        providers.Singleton(lambda: mock_message_queue)
    )

    # Mock KBRagResponse for rag_retrieval_router
    mock_kb_rag_response = AsyncMock()
    mock_kb_rag_response.retrieve_documents.return_value = [{'doc': 'test doc'}]
    mock_kb_rag_response.query.return_value = {'response': 'test response'}
    knowledge_base_container.knowledge_base_retrieve.override(
        providers.Singleton(lambda: mock_kb_rag_response)
    )

    # Mock ImageRagRetrieve for rag_retrieval_router
    mock_image_rag_retrieve = AsyncMock()
    mock_image_rag_retrieve.retrieve_images.return_value = {
        'image_response': 'test image response'
    }
    knowledge_base_container.image_knowledge_base_retrieve.override(
        providers.Singleton(lambda: mock_image_rag_retrieve)
    )
    mock_cloud_storage_manager_instance = Mock()
    mock_cloud_storage_manager_instance.file_protocol.return_value = 'gs'

    test_config_dict = {
        'model': {'inference_service_url': 'http://mock-inference-url.com'},
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
    knowledge_base_container.config.from_dict(test_config_dict)

    yield (
        auth_container,
        common_container,
        user_container,
        knowledge_base_container,
        llm_inference_config_container,
    )
    auth_container.unwire()
    common_container.unwire()
    user_container.unwire()


@pytest.fixture
def test_client(setup_containers):
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(RequireAuthMiddleware)
    app.include_router(knowledge_base_router, prefix='/floware')
    app.include_router(kb_document_router, prefix='/floware')
    app.include_router(rag_retrieval_router, prefix='/floware')
    return TestClient(app)


@pytest.fixture
def auth_token(setup_containers, test_user_id, test_session_id):
    auth_container, _, _, _, _ = setup_containers
    token_service = auth_container.token_service()
    token = token_service.create_token(
        sub='test@example.com',
        user_id=test_user_id,
        role_id='test_role_id',
        session_id=test_session_id,
    )
    return token
