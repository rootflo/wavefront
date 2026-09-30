"""
Tests for /floware/v1/store_embedding validating each document separately:
valid documents are stored, invalid ones are listed under `rejected`, and the
request fails with 400 only when every document is rejected.
"""

from uuid import uuid4

import pytest
from db_repo_module.models.knowledge_base_documents import KnowledgeBaseDocuments
from db_repo_module.models.knowledge_base_embeddings import KnowledgeBaseEmbeddings
from db_repo_module.models.knowledge_bases import KnowledgeBase
from fastapi import status
from flo_testing import seed_user_session as create_session
from sqlalchemy import select

STORE_URL = '/floware/v1/store_embedding'


async def create_kb(test_session, vector_size: int, vector_size_1: int = 0):
    kb_id = uuid4()
    async with test_session() as session:
        session.add(
            KnowledgeBase(
                id=kb_id,
                name=f'KB {kb_id}',
                description='store validation test',
                type='document',
                vector_size=vector_size,
                vector_size_1=vector_size_1,
            )
        )
        await session.commit()
    return kb_id


async def create_doc(test_session, kb_id):
    doc_id = uuid4()
    async with test_session() as session:
        session.add(
            KnowledgeBaseDocuments(
                id=doc_id,
                knowledge_base_id=kb_id,
                file_path=f'bucket/{doc_id}',
                file_name=str(doc_id),
                file_type='pdf',
                file_size=10,
            )
        )
        await session.commit()
    return doc_id


async def stored_doc_ids(test_session, *doc_ids):
    async with test_session() as session:
        result = await session.execute(
            select(KnowledgeBaseEmbeddings.document_id).where(
                KnowledgeBaseEmbeddings.document_id.in_(doc_ids)
            )
        )
        return sorted(str(row[0]) for row in result.all())


def text_doc(kb_id, doc_id, vectors):
    return {
        'embedding_vector': vectors,
        'document_id': str(doc_id),
        'kb_id': str(kb_id),
        'chunk_text': [f'chunk {i}' for i in range(len(vectors))],
        'chunk_index': [f'chunk_{i}' for i in range(len(vectors))],
    }


def image_doc(kb_id, doc_id, clip, dino):
    return {
        'embedding_vector': [clip],
        'embedding_vector_1': [dino],
        'document_id': str(doc_id),
        'kb_id': str(kb_id),
        'chunk_text': ['image data'],
        'chunk_index': ['chunk_0'],
    }


def store(test_client, auth_token, *docs):
    return test_client.post(
        STORE_URL,
        headers={'Authorization': f'Bearer {auth_token}'},
        json={'embeddings': list(docs)},
    )


def rejected_by_doc(response):
    return {
        item['document_id']: item['reason']
        for item in response.json()['data']['rejected']
    }


@pytest.fixture
async def seeded(test_session, test_user_id, test_session_id):
    await create_session(test_session, test_user_id, test_session_id)


@pytest.mark.asyncio
async def test_bad_documents_are_rejected_and_the_rest_stored(
    seeded, test_client, auth_token, test_session
):
    kb_id = await create_kb(test_session, vector_size=3)
    good, wrong_size, empty = [await create_doc(test_session, kb_id) for _ in range(3)]
    missing_kb_doc = uuid4()

    response = store(
        test_client,
        auth_token,
        text_doc(kb_id, good, [[0.1, 0.2, 0.3]]),
        text_doc(kb_id, wrong_size, [[0.1, 0.2]]),
        text_doc(kb_id, empty, []),
        text_doc(uuid4(), missing_kb_doc, [[0.1, 0.2, 0.3]]),
    )

    assert response.status_code == status.HTTP_200_OK
    rejected = rejected_by_doc(response)
    assert set(rejected) == {str(wrong_size), str(empty), str(missing_kb_doc)}
    assert 'vector size' in rejected[str(wrong_size)]
    assert rejected[str(empty)] == 'The document has no embeddings'
    assert (
        rejected[str(missing_kb_doc)] == 'There is no knowledge bases based on the id'
    )
    assert await stored_doc_ids(test_session, good, wrong_size, empty) == [str(good)]


@pytest.mark.asyncio
async def test_image_into_text_kb_is_rejected_even_when_sizes_match(
    seeded, test_client, auth_token, test_session
):
    # Primary vector sizes match, so only the second (DINO) vector gives it away
    kb_id = await create_kb(test_session, vector_size=3)
    doc_id = await create_doc(test_session, kb_id)

    response = store(
        test_client, auth_token, image_doc(kb_id, doc_id, [0.1, 0.2, 0.3], [0.4, 0.5])
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'only accepts one' in response.json()['meta']['error']
    assert await stored_doc_ids(test_session, doc_id) == []


@pytest.mark.asyncio
async def test_text_into_image_kb_is_rejected(
    seeded, test_client, auth_token, test_session
):
    kb_id = await create_kb(test_session, vector_size=3, vector_size_1=2)
    doc_id = await create_doc(test_session, kb_id)

    response = store(
        test_client, auth_token, text_doc(kb_id, doc_id, [[0.1, 0.2, 0.3]])
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'vector size' in response.json()['meta']['error']


@pytest.mark.asyncio
async def test_image_into_image_kb_is_stored(
    seeded, test_client, auth_token, test_session
):
    kb_id = await create_kb(test_session, vector_size=3, vector_size_1=2)
    doc_id = await create_doc(test_session, kb_id)

    response = store(
        test_client, auth_token, image_doc(kb_id, doc_id, [0.1, 0.2, 0.3], [0.4, 0.5])
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['data']['rejected'] == []
    assert await stored_doc_ids(test_session, doc_id) == [str(doc_id)]


@pytest.mark.asyncio
async def test_multi_chunk_text_doc_without_second_vector_is_stored(
    seeded, test_client, auth_token, test_session
):
    # embedding_vector_1 omitted: its [[]] default used to be indexed per
    # chunk, raising IndexError from the second chunk on
    kb_id = await create_kb(test_session, vector_size=3)
    doc_id = await create_doc(test_session, kb_id)

    response = store(
        test_client,
        auth_token,
        text_doc(kb_id, doc_id, [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]]),
    )

    assert response.status_code == status.HTTP_200_OK
    assert await stored_doc_ids(test_session, doc_id) == [str(doc_id)] * 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('override', 'reason_fragment'),
    [
        ({'chunk_text': []}, 'same length'),
        ({'chunk_index': ['0']}, 'chunk_<number>'),
    ],
)
async def test_malformed_document_is_rejected_with_400(
    seeded, test_client, auth_token, test_session, override, reason_fragment
):
    kb_id = await create_kb(test_session, vector_size=3)
    doc_id = await create_doc(test_session, kb_id)

    response = store(
        test_client,
        auth_token,
        {**text_doc(kb_id, doc_id, [[0.1, 0.2, 0.3]]), **override},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert reason_fragment in response.json()['meta']['error']
