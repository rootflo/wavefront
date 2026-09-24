"""Test wiring specific to knowledge_base_module."""

from io import BytesIO
from unittest.mock import AsyncMock
from unittest.mock import Mock

import pytest
from dependency_injector import providers
from flo_testing import make_test_client
from knowledge_base_module.controllers.knowledge_base_controller import (
    knowledge_base_router,
)
from knowledge_base_module.controllers.knowledge_base_document_controller import (
    kb_document_router,
)
from knowledge_base_module.controllers.rag_retreival_controller import (
    rag_retrieval_router,
)
from knowledge_base_module.knowledge_base_container import KnowledgeBaseContainer
from llm_inference_config_module.container import LlmInferenceConfigContainer

KB_CONFIG = {
    'model': {'inference_service_url': 'http://mock-inference-url.com'},
    'cloud': {'provider': 'gcp'},
    'storage': {'application_bucket': 'test_bucket'},
}


@pytest.fixture
def setup_containers(core_containers):
    # Both of these take the mocked cache manager. The previous version handed
    # them db_repo_container.cache_manager, which is the real Redis-backed
    # provider, contradicting its own "avoid Redis connection" comment.
    cloud_storage_manager = Mock()
    cloud_storage_manager.file_protocol = Mock(return_value='gs')
    cloud_storage_manager.save_small_file = Mock()
    cloud_storage_manager.save_large_file = Mock()
    cloud_storage_manager.get_file = Mock(return_value=BytesIO(b'file content'))
    cloud_storage_manager.read_file = Mock(return_value=b'file content')

    message_queue = Mock()
    message_queue.add_message = Mock(return_value='message_id_123')

    llm_inference_config_container = LlmInferenceConfigContainer(
        db_client=core_containers.db_client,
        cache_manager=core_containers.cache_manager,
    )
    knowledge_base_container = KnowledgeBaseContainer(
        db_client=core_containers.db_client,
        cache_manager=core_containers.cache_manager,
        cloud_storage_manager=cloud_storage_manager,
        rag_queue=message_queue,
    )

    kb_rag_response = AsyncMock()
    kb_rag_response.retrieve_documents.return_value = [{'doc': 'test doc'}]
    kb_rag_response.query.return_value = {'response': 'test response'}
    knowledge_base_container.knowledge_base_retrieve.override(
        providers.Singleton(lambda: kb_rag_response)
    )

    image_rag_retrieve = AsyncMock()
    image_rag_retrieve.retrieve_images.return_value = {
        'image_response': 'test image response'
    }
    knowledge_base_container.image_knowledge_base_retrieve.override(
        providers.Singleton(lambda: image_rag_retrieve)
    )

    knowledge_base_container.config.from_dict(KB_CONFIG)

    core_containers.wire(
        core_containers.auth,
        packages=['user_management_module.authorization'],
    )
    core_containers.wire(
        core_containers.user,
        packages=['user_management_module.authorization'],
    )
    core_containers.wire(
        core_containers.common,
        packages=[
            'user_management_module.authorization',
            'knowledge_base_module.controllers',
        ],
    )
    core_containers.wire(
        knowledge_base_container,
        packages=['knowledge_base_module.controllers'],
    )
    core_containers.wire(
        llm_inference_config_container,
        packages=['knowledge_base_module.controllers'],
    )

    return (
        core_containers.auth,
        core_containers.common,
        core_containers.user,
        knowledge_base_container,
        llm_inference_config_container,
    )


@pytest.fixture
def test_client(setup_containers):
    return make_test_client(
        knowledge_base_router, kb_document_router, rag_retrieval_router
    )
