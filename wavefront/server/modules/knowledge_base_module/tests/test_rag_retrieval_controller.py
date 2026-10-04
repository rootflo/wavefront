from unittest.mock import AsyncMock
from uuid import uuid4
from db_repo_module.models.knowledge_bases import KnowledgeBase
from db_repo_module.models.knowledge_base_documents import KnowledgeBaseDocuments
from dependency_injector import providers
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import status
from flo_testing import seed_user_session as create_session


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
            type='text',
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
async def test_retrieve_image_exact_match_returns_document_date(
    test_client,
    auth_token,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    setup_containers,
):
    """Exact-match (branch-level repeat-pledge) results must include each
    hit's `document_date`, since callers (e.g. aurum) need it to bucket
    matches into their own lookback windows."""
    await create_session(test_session, test_user_id, test_session_id)

    _, _, _, kb_container, _ = setup_containers

    kb_id = uuid4()
    async with test_session() as session:
        new_kb = KnowledgeBase(
            id=kb_id,
            name='Test KB Exact Match',
            description='Test Description',
            type='image',
            vector_size=0,
        )
        session.add(new_kb)
        await session.commit()

    mock_image_rag_retrieve = AsyncMock()
    mock_image_rag_retrieve.exact_match_dino.return_value = [
        {
            'document_id': str(uuid4()),
            'file_path': 'images/test.png',
            'file_name': 'test.png',
            'document_date': '2026-08-01T00:00:00',
            'dino_score': 0.95,
        }
    ]
    kb_container.image_knowledge_base_retrieve.override(
        providers.Singleton(lambda: mock_image_rag_retrieve)
    )

    response = test_client.post(
        f'/floware/v1/knowledge-base/{kb_id}/retrieve',
        params={
            'exact_match': 'true',
            'filter1': 'branch-1',
            'document_date_start': '2026-07-01T00:00:00',
            'document_date_end': '2026-08-15T00:00:00',
            'threshold': 0.8,
        },
        headers={'Authorization': f'Bearer {auth_token}'},
        json={'image_data': 'base64-image-data'},
    )

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data['data']['match_count'] == 1
    documents = response_data['data']['documents']
    assert len(documents) == 1
    assert documents[0]['document_date'] == '2026-08-01T00:00:00'

    mock_image_rag_retrieve.exact_match_dino.assert_awaited_once()


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
            type='text',
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
            type='text',
            vector_size=1024,
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
        'text_embedding': [[0.1] * 1024],  # BGE-M3 dense
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
            type='text',
            vector_size=1024,
        )
        session.add(new_kb)
        await session.commit()

    embedding_payload = {
        'text_embedding': [[0.1, 0.2, 0.3]],  # Incorrect size (BGE-M3 is 1024)
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


def test_legacy_retrieve_endpoint_is_removed(test_client, auth_token):
    # Replaced by /v1/knowledge-base/{kb_id}/retrieve
    response = test_client.post(
        '/floware/v1/retrieve',
        headers={'Authorization': f'Bearer {auth_token}'},
        json={'query': 'q', 'kb_id': str(uuid4())},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


# --- result count: limit overrides top_k, default 10, for every mode ---------


async def _seed_kb(test_session, test_user_id, test_session_id):
    await create_session(test_session, test_user_id, test_session_id)
    kb_id = uuid4()
    async with test_session() as session:
        session.add(
            KnowledgeBase(
                id=kb_id,
                name='Result count KB',
                description='',
                type='text',
                vector_size=1024,
            )
        )
        await session.commit()
    return kb_id


def _mock_retrieval(kb_container):
    text = AsyncMock()
    text.retrieve_documents.return_value = [{'doc': 'text doc'}]
    image = AsyncMock()
    image.retrieve_images.return_value = [{'doc': 'image doc'}]
    kb_container.knowledge_base_retrieve.override(providers.Singleton(lambda: text))
    kb_container.image_knowledge_base_retrieve.override(
        providers.Singleton(lambda: image)
    )
    return text, image


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('params', 'expected'),
    [({'top_k': 3}, 3), ({'limit': 4}, 4), ({'top_k': 3, 'limit': 7}, 7), ({}, 10)],
)
async def test_text_search_result_count(
    test_client,
    auth_token,
    test_session,
    test_user_id,
    test_session_id,
    setup_containers,
    params,
    expected,
):
    kb_id = await _seed_kb(test_session, test_user_id, test_session_id)
    text, _ = _mock_retrieval(setup_containers[3])

    response = test_client.post(
        f'/floware/v1/knowledge-base/{kb_id}/retrieve',
        headers={'Authorization': f'Bearer {auth_token}'},
        params={'query': 'hello', **params},
    )

    assert response.status_code == status.HTTP_200_OK
    # retrieve_documents(query, kb_id, threshold, vector_weight,
    #                    keyword_weight, query_filter, offset, limit, ...)
    assert text.retrieve_documents.await_args.args[7] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('params', 'expected'),
    [({'top_k': 3}, 3), ({'limit': 4}, 4), ({'top_k': 3, 'limit': 7}, 7), ({}, 10)],
)
async def test_image_search_result_count(
    test_client,
    auth_token,
    test_session,
    test_user_id,
    test_session_id,
    setup_containers,
    params,
    expected,
):
    kb_id = await _seed_kb(test_session, test_user_id, test_session_id)
    _, image = _mock_retrieval(setup_containers[3])

    response = test_client.post(
        f'/floware/v1/knowledge-base/{kb_id}/retrieve',
        headers={'Authorization': f'Bearer {auth_token}'},
        params=params,
        json={'image_data': 'base64-image-data'},
    )

    assert response.status_code == status.HTTP_200_OK
    # retrieve_images(image_data, inference_url, kb_id, top_k, ...)
    assert image.retrieve_images.await_args.args[3] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize('params', [{'top_k': 0}, {'limit': 0}, {'top_k': -5}])
async def test_non_positive_result_counts_are_rejected(
    test_client,
    auth_token,
    test_session,
    test_user_id,
    test_session_id,
    setup_containers,
    params,
):
    kb_id = await _seed_kb(test_session, test_user_id, test_session_id)
    text, _ = _mock_retrieval(setup_containers[3])

    response = test_client.post(
        f'/floware/v1/knowledge-base/{kb_id}/retrieve',
        headers={'Authorization': f'Bearer {auth_token}'},
        params={'query': 'hello', **params},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    text.retrieve_documents.assert_not_awaited()


def test_image_queries_no_longer_receive_a_missing_top_k():
    # The CLIP-only/DINO-only image queries did int(params.get('top_k', 10)),
    # which crashed on top_k=None; the controller now always passes a number.
    from knowledge_base_module.controllers.rag_retreival_controller import (
        _result_limit,
    )

    assert _result_limit(None, None) == 10
    assert _result_limit(5, None) == 5
    assert _result_limit(5, 2) == 2


# --- query embedding failures map to 503 / 502 --------------------------------

from knowledge_base_module.embeddings.embed import TextEmbeddingError  # noqa: E402

EMBEDDING_FAILURES = [
    (TextEmbeddingError('model still loading', status_code=503), 503),
    (TextEmbeddingError('rate limited', status_code=429), 503),
    (TextEmbeddingError('inference crashed', status_code=500), 502),
    (TextEmbeddingError('connection refused'), 502),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(('error', 'expected_status'), EMBEDDING_FAILURES)
async def test_retrieve_maps_embedding_failures(
    test_client,
    auth_token,
    test_session,
    test_user_id,
    test_session_id,
    setup_containers,
    error,
    expected_status,
):
    kb_id = await _seed_kb(test_session, test_user_id, test_session_id)
    text, _ = _mock_retrieval(setup_containers[3])
    text.retrieve_documents.side_effect = error

    response = test_client.post(
        f'/floware/v1/knowledge-base/{kb_id}/retrieve',
        headers={'Authorization': f'Bearer {auth_token}'},
        params={'query': 'hello'},
    )

    assert response.status_code == expected_status
    assert 'Could not embed the query' in response.json()['meta']['error']


@pytest.mark.parametrize(
    ('method', 'path'),
    [
        ('post', 'augment/{inference_id}'),
        ('post', 'inference'),
        ('get', 'inference'),
        ('delete', 'inference/{inference_id}'),
    ],
)
def test_kb_inference_endpoints_are_removed(test_client, auth_token, method, path):
    # RAG over a knowledge base now goes through the chatbot feature
    url = f'/floware/v1/knowledge-base/{uuid4()}/' + path.format(inference_id=uuid4())

    response = getattr(test_client, method)(
        url, headers={'Authorization': f'Bearer {auth_token}'}
    )

    assert response.status_code in (
        status.HTTP_404_NOT_FOUND,
        status.HTTP_405_METHOD_NOT_ALLOWED,
    )
