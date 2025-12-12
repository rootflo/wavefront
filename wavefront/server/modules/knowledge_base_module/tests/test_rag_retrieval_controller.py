from unittest.mock import AsyncMock
from uuid import uuid4
from db_repo_module.models.knowledge_bases import KnowledgeBase
from db_repo_module.models.session import Session
from db_repo_module.models.user import User
from db_repo_module.models.kb_inferences import KnowledgeBaseInferences
from db_repo_module.models.knowledge_base_documents import KnowledgeBaseDocuments
from db_repo_module.models.llm_inference_config import LlmInferenceConfig
from dependency_injector import providers
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import status


async def create_session(test_session: AsyncSession, test_user_id, test_session_id):
    user = User(
        id=test_user_id,
        email='test@example.com',
        password='hashed_password',
        first_name='Test',
        last_name='User',
    )

    # Create a session in the database
    db_session = Session(
        id=test_session_id, user_id=test_user_id, device_info='test_device'
    )

    async with test_session() as session:
        session.add(user)
        session.add(db_session)
        await session.commit()


@pytest.mark.asyncio
async def test_retrieve_query_success(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a knowledge base
    kb_id = uuid4()
    async with test_session() as session:
        new_kb = KnowledgeBase(
            id=kb_id,
            name='Test KB for Retrieve',
            description='Test Description',
            type='document',
            vector_size=1536,
        )
        session.add(new_kb)
        await session.commit()

    query = 'test query'
    response = test_client.post(
        f'/floware/v1/knowledge-base/{kb_id}/retrieve?query={query}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data['data']['documents'] == [{'doc': 'test doc'}]


@pytest.mark.asyncio
async def test_retrieve_query_empty_query(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    kb_id = uuid4()
    response = test_client.post(
        f'/floware/v1/knowledge-base/{kb_id}/retrieve?query=',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    response_data = response.json()
    assert response_data['meta']['error'] == 'Query or Image data should not be empty'


@pytest.mark.asyncio
async def test_retrieve_image_success(
    test_client,
    auth_token,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    setup_containers,
):
    await create_session(test_session, test_user_id, test_session_id)

    _, _, _, kb_container, _ = setup_containers

    kb_id = uuid4()
    async with test_session() as session:
        new_kb = KnowledgeBase(
            id=kb_id,
            name='Test KB Image Retrieve',
            description='Test Description',
            type='image',
            vector_size=0,
        )
        session.add(new_kb)
        await session.commit()

    mock_image_rag_retrieve = AsyncMock()
    mock_image_rag_retrieve.retrieve_images.return_value = [
        {
            'doc': 'image doc',
            'file_path': 'images/test.png',
        }
    ]
    kb_container.image_knowledge_base_retrieve.override(
        providers.Singleton(lambda: mock_image_rag_retrieve)
    )

    response = test_client.post(
        f'/floware/v1/knowledge-base/{kb_id}/retrieve',
        headers={'Authorization': f'Bearer {auth_token}'},
        json={'image_data': 'base64-image-data'},
    )

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    documents = response_data['data']['documents']
    assert len(documents) == 1
    assert documents[0]['doc'] == 'image doc'

    mock_image_rag_retrieve.retrieve_images.assert_awaited_once()


@pytest.mark.asyncio
async def test_retrieve_image_kb_not_found(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    non_existent_kb_id = uuid4()
    response = test_client.post(
        f'/floware/v1/knowledge-base/{non_existent_kb_id}/retrieve',
        headers={'Authorization': f'Bearer {auth_token}'},
        json={'image_data': 'base64-image-data'},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    response_data = response.json()
    assert (
        response_data['meta']['error']
        == 'Knowledge Base with the mentioned id doesnt exist'
    )


@pytest.mark.asyncio
async def test_retrieve_query_kb_not_found(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    non_existent_kb_id = uuid4()
    query = 'test query'
    response = test_client.post(
        f'/floware/v1/knowledge-base/{non_existent_kb_id}/retrieve?query={query}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    response_data = response.json()
    assert (
        response_data['meta']['error']
        == 'Knowledge Base with the mentioned id doesnt exist'
    )


@pytest.mark.asyncio
async def test_retrieve_query_no_matching_documents(
    test_client,
    auth_token,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    setup_containers,
):
    await create_session(test_session, test_user_id, test_session_id)

    _, _, _, kb_container, _ = setup_containers

    # Create a knowledge base
    kb_id = uuid4()
    async with test_session() as session:
        new_kb = KnowledgeBase(
            id=kb_id,
            name='Test KB for No Docs',
            description='Test Description',
            type='document',
            vector_size=1536,
        )
        session.add(new_kb)
        await session.commit()

    # Override the mock to return empty results for retrieve_documents
    mock_kb_rag_response = AsyncMock()
    mock_kb_rag_response.retrieve_documents.return_value = []
    kb_container.knowledge_base_retrieve.override(
        providers.Singleton(lambda: mock_kb_rag_response)
    )

    query = 'query with no matches'
    response = test_client.post(
        f'/floware/v1/knowledge-base/{kb_id}/retrieve?query={query}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_retrieve_image_data_empty(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    kb_id = uuid4()
    response = test_client.post(
        f'/floware/v1/knowledge-base/{kb_id}/retrieve',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    response_data = response.json()
    assert response_data['meta']['error'] == 'Query or Image data should not be empty'


@pytest.mark.asyncio
async def test_rag_response_with_query_success(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a knowledge base and an inference
    kb_id = uuid4()
    inference_id = uuid4()
    config_id = uuid4()
    async with test_session() as session:
        new_kb = KnowledgeBase(
            id=kb_id,
            name='Test KB RAG Query',
            description='Test Description',
            type='document',
            vector_size=1536,
        )
        llm_config = LlmInferenceConfig(
            id=config_id,
            llm_model='gemini-2.5-flash',
            display_name='test_root_gemini',
            api_key='test-api-key-placeholder',
            type='gemini',
            base_url='https://generativelanguage.googleapis.com/',
        )
        new_inference = KnowledgeBaseInferences(
            inference_id=inference_id,
            knowledge_base_id=kb_id,
            inference_content={'prompt': 'System prompt'},
            config_id=config_id,
        )
        session.add(new_kb)
        await session.commit()
        session.add(llm_config)
        await session.commit()
        session.add(new_inference)
        await session.commit()

    query = 'user query'
    model = 'gemini-2.5-pro'
    response = test_client.post(
        f'/floware/v1/knowledge-base/{kb_id}/augment/{inference_id}?query={query}&model={model}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data['data']['response'] == {'response': 'test response'}


@pytest.mark.asyncio
async def test_rag_response_empty_query(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    kb_id = uuid4()
    inference_id = uuid4()
    config_id = uuid4()
    async with test_session() as session:
        new_kb = KnowledgeBase(
            id=kb_id,
            name='Test KB RAG Query',
            description='Test Description',
            type='document',
            vector_size=1536,
        )
        llm_config = LlmInferenceConfig(
            id=config_id,
            llm_model='gemini-2.5-flash',
            display_name='test_root_gemini',
            api_key='test-api-key-placeholder',
            type='gemini',
            base_url='https://generativelanguage.googleapis.com/',
        )
        new_inference = KnowledgeBaseInferences(
            inference_id=inference_id,
            knowledge_base_id=kb_id,
            inference_content={'prompt': 'System prompt'},
            config_id=config_id,
        )
        session.add(new_kb)
        await session.commit()
        session.add(llm_config)
        await session.commit()
        session.add(new_inference)
        await session.commit()
    response = test_client.post(
        f'/floware/v1/knowledge-base/{kb_id}/augment/{inference_id}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    response_data = response.json()
    assert (
        response_data['meta']['error']
        == 'Query must be provided either in request body or as query parameter'
    )


@pytest.mark.asyncio
async def test_rag_response_kb_not_found(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    non_existent_kb_id = uuid4()
    inference_id = uuid4()
    query = 'test query'
    model = 'gemini-2.5-pro'
    response = test_client.post(
        f'/floware/v1/knowledge-base/{non_existent_kb_id}/augment/{inference_id}?query={query}&model={model}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    response_data = response.json()
    assert (
        response_data['meta']['error']
        == 'Knowledge Base with the mentioned id doesnt exist'
    )


@pytest.mark.asyncio
async def test_rag_response_inference_not_found(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a knowledge base
    kb_id = uuid4()
    async with test_session() as session:
        new_kb = KnowledgeBase(
            id=kb_id,
            name='Test KB RAG No Inference',
            description='Test Description',
            type='document',
            vector_size=1536,
        )
        session.add(new_kb)
        await session.commit()

    non_existent_inference_id = uuid4()
    query = 'test query'
    model = 'gemini-2.5-pro'
    response = test_client.post(
        f'/floware/v1/knowledge-base/{kb_id}/augment/{non_existent_inference_id}?query={query}&model={model}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    response_data = response.json()
    assert (
        response_data['meta']['error']
        == 'Knowledge Base inference with the mentioned knowledge_base_id and inference_id doesnt exist'
    )


@pytest.mark.asyncio
async def test_create_system_prompt_success(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a knowledge base
    kb_id = uuid4()
    inference_id = uuid4()
    config_id = uuid4()
    async with test_session() as session:
        new_kb = KnowledgeBase(
            id=kb_id,
            name='Test KB RAG Query',
            description='Test Description',
            type='document',
            vector_size=1536,
        )
        llm_config = LlmInferenceConfig(
            id=config_id,
            llm_model='gemini-2.5-flash',
            display_name='test_root_gemini',
            api_key='test-api-key-placeholder',
            type='gemini',
            base_url='https://generativelanguage.googleapis.com/',
        )
        new_inference = KnowledgeBaseInferences(
            inference_id=inference_id,
            knowledge_base_id=kb_id,
            inference_content={'prompt': 'System prompt'},
            config_id=config_id,
        )
        session.add(new_kb)
        await session.commit()
        session.add(llm_config)
        await session.commit()
        session.add(new_inference)
        await session.commit()

    prompt_payload = {'prompt': 'This is a test system prompt.'}
    response = test_client.post(
        f'/floware/v1/knowledge-base/{kb_id}/llm_config/{config_id}/inference',
        headers={'Authorization': f'Bearer {auth_token}'},
        json=prompt_payload,
    )

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert (
        response_data['data']['message']
        == 'Created the knowledge base inference table successfully'
    )
    assert 'inference_id' in response_data['data']


@pytest.mark.asyncio
async def test_get_system_prompt_success(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a knowledge base and a system prompt
    kb_id = uuid4()
    async with test_session() as session:
        new_kb = KnowledgeBase(
            id=kb_id,
            name='Test KB Get Prompt',
            description='Test Description',
            type='document',
            vector_size=1536,
        )
        session.add(new_kb)
        await session.commit()
        new_inference = KnowledgeBaseInferences(
            knowledge_base_id=kb_id,
            inference_content={'message': 'Existing system prompt'},
        )
        session.add(new_inference)
        await session.commit()

    response = test_client.get(
        f'/floware/v1/knowledge-base/{kb_id}/inference',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert len(response_data['data']['resources']) == 1
    assert response_data['data']['resources'][0]['inference_content'] == {
        'message': 'Existing system prompt'
    }


@pytest.mark.asyncio
async def test_get_system_prompt_no_prompt_found(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a knowledge base but no system prompt
    kb_id = uuid4()
    async with test_session() as session:
        new_kb = KnowledgeBase(
            id=kb_id,
            name='Test KB Get No Prompt',
            description='Test Description',
            type='document',
            vector_size=1536,
        )
        session.add(new_kb)
        await session.commit()

    response = test_client.get(
        f'/floware/v1/knowledge-base/{kb_id}/inference',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert len(response_data['data']['resources']) == 0


@pytest.mark.asyncio
async def test_store_embeddings_success(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a knowledge base
    kb_id = uuid4()
    doc_id = uuid4()
    async with test_session() as session:
        new_kb = KnowledgeBase(
            id=kb_id,
            name='Test KB Embeddings',
            description='Test Description',
            type='document',
            vector_size=3,
            vector_size_1=0,
        )
        session.add(new_kb)
        await session.commit()
        new_kb_document_2 = KnowledgeBaseDocuments(
            id=doc_id,
            knowledge_base_id=kb_id,
            file_path='gcs_url/doc2.pdf',
            file_name='doc2.pdf',
            file_type='pdf',
            file_size=1000,
        )
        session.add(new_kb_document_2)
        await session.commit()

    embedding_payload = {
        'embedding_vector': [[0.1, 0.2, 0.3]],
        'document_id': str(doc_id),
        'kb_id': str(kb_id),
        'chunk_text': ['chunk 1'],
        'chunk_index': ['chunk_0'],
    }

    doc_wise_payload = {
        'embeddings': [
            embedding_payload
        ]  # <-- Wrap it in a list under the 'embeddings' key
    }

    response = test_client.post(
        '/floware/v1/store_embedding',
        headers={'Authorization': f'Bearer {auth_token}'},
        json=doc_wise_payload,
    )

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert (
        response_data['data']['message']
        == 'Created the knowledge base documents and embeddings successfully'
    )


@pytest.mark.asyncio
async def test_store_embeddings_kb_not_found(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    non_existent_kb_id = uuid4()
    doc_id = uuid4()
    embedding_payload = {
        'embedding_vector': [[0.1, 0.2, 0.3]],
        'document_id': str(doc_id),
        'kb_id': str(non_existent_kb_id),
        'chunk_text': ['chunk 1'],
        'chunk_index': ['chunk_0'],
    }

    doc_wise_payload = {'embeddings': [embedding_payload]}

    response = test_client.post(
        '/floware/v1/store_embedding',
        headers={'Authorization': f'Bearer {auth_token}'},
        json=doc_wise_payload,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    response_data = response.json()
    assert (
        response_data['meta']['error'] == 'There is no knowledge bases based on the id'
    )


@pytest.mark.asyncio
async def test_store_embeddings_vector_size_mismatch(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a knowledge base with a specific vector size
    kb_id = uuid4()
    doc_id = uuid4()
    async with test_session() as session:
        new_kb = KnowledgeBase(
            id=kb_id,
            name='Test KB Vector Size Mismatch',
            description='Test Description',
            type='document',
            vector_size=10,
            vector_size_1=0,
        )
        session.add(new_kb)
        await session.commit()

    embedding_payload = {
        'embedding_vector': [[0.1, 0.2, 0.3]],  # Incorrect size
        'document_id': str(doc_id),
        'kb_id': str(kb_id),
        'chunk_text': ['chunk 1'],
        'chunk_index': ['chunk_0'],
    }

    doc_wise_payload = {'embeddings': [embedding_payload]}

    response = test_client.post(
        '/floware/v1/store_embedding',
        headers={'Authorization': f'Bearer {auth_token}'},
        json=doc_wise_payload,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    response_data = response.json()
    assert (
        response_data['meta']['error']
        == "The vector size on the embedding doesn't match the required embedding vector size"
    )
