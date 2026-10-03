"""
Tests for /floware/v1/store_embedding validating each document separately:
valid documents are stored, invalid ones are listed under `rejected`, and the
request fails with 400 only when every document is rejected.

A knowledge base's type decides what it stores: text knowledge bases take
BGE-M3 text embeddings, image knowledge bases take CLIP + DINO embeddings.
"""

from uuid import uuid4

import pytest
from db_repo_module.models.knowledge_base_documents import KnowledgeBaseDocuments
from db_repo_module.models.knowledge_base_embeddings import KnowledgeBaseEmbeddings
from db_repo_module.models.knowledge_bases import (
    KB_VECTOR_SIZES,
    KnowledgeBase,
    KnowledgeBaseType,
)
from fastapi import status
from flo_testing import seed_user_session as create_session
from sqlalchemy import select

STORE_URL = '/floware/v1/store_embedding'
TEXT_DIM = 1024
CLIP_DIM, DINO_DIM = KB_VECTOR_SIZES[KnowledgeBaseType.IMAGE]


async def create_kb(test_session, kb_type: str = 'text'):
    vector_size, vector_size_1 = KB_VECTOR_SIZES[KnowledgeBaseType(kb_type)]
    kb_id = uuid4()
    async with test_session() as session:
        session.add(
            KnowledgeBase(
                id=kb_id,
                name=f'KB {kb_id}',
                description='store validation test',
                type=kb_type,
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


def bge_doc(kb_id, doc_id, chunks=1, dense_dim=TEXT_DIM, sparse=None):
    """A text document: BGE-M3 dense (+ sparse) vectors per chunk."""
    doc = {
        'text_embedding': [[0.01] * dense_dim for _ in range(chunks)],
        'document_id': str(doc_id),
        'kb_id': str(kb_id),
        'chunk_text': [f'chunk {i}' for i in range(chunks)],
        'chunk_index': [f'chunk_{i}' for i in range(chunks)],
    }
    doc['text_sparse_embedding'] = (
        sparse
        if sparse is not None
        else [{'indices': [5, 99], 'values': [0.3, 0.2]} for _ in range(chunks)]
    )
    return doc


def image_doc(kb_id, doc_id, chunks=1, clip_dim=CLIP_DIM, dino_dim=DINO_DIM, dino=True):
    """An image document: CLIP (+ DINO) vectors per chunk."""
    doc = {
        'embedding_vector': [[0.1] * clip_dim for _ in range(chunks)],
        'document_id': str(doc_id),
        'kb_id': str(kb_id),
        'chunk_text': ['image data'] * chunks,
        'chunk_index': [f'chunk_{i}' for i in range(chunks)],
    }
    if dino:
        doc['embedding_vector_1'] = [[0.2] * dino_dim for _ in range(chunks)]
    return doc


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


def error(response) -> str:
    return response.json()['meta']['error']


async def stored_text_rows(test_session, doc_id):
    async with test_session() as session:
        result = await session.execute(
            select(
                KnowledgeBaseEmbeddings.chunk_index,
                KnowledgeBaseEmbeddings.text_embedding,
                KnowledgeBaseEmbeddings.text_sparse_embedding,
                KnowledgeBaseEmbeddings.embedding_vector,
            )
            .where(KnowledgeBaseEmbeddings.document_id == doc_id)
            .order_by(KnowledgeBaseEmbeddings.chunk_index)
        )
        return result.all()


@pytest.fixture
async def seeded(test_session, test_user_id, test_session_id):
    await create_session(test_session, test_user_id, test_session_id)


# --- per-document validation -------------------------------------------------


@pytest.mark.asyncio
async def test_bad_documents_are_rejected_and_the_rest_stored(
    seeded, test_client, auth_token, test_session
):
    kb_id = await create_kb(test_session, 'text')
    good, wrong_size, empty = [await create_doc(test_session, kb_id) for _ in range(3)]
    missing_kb_doc = uuid4()

    response = store(
        test_client,
        auth_token,
        bge_doc(kb_id, good),
        bge_doc(kb_id, wrong_size, dense_dim=3),
        {**bge_doc(kb_id, empty, chunks=0), 'text_sparse_embedding': []},
        bge_doc(uuid4(), missing_kb_doc),
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
    kb_id = await create_kb(test_session, 'text')
    doc_id = await create_doc(test_session, kb_id)

    response = store(test_client, auth_token, {**bge_doc(kb_id, doc_id), **override})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert reason_fragment in error(response)


@pytest.mark.asyncio
async def test_document_with_both_text_and_image_vectors_is_rejected(
    seeded, test_client, auth_token, test_session
):
    kb_id = await create_kb(test_session, 'text')
    doc_id = await create_doc(test_session, kb_id)
    doc = {**bge_doc(kb_id, doc_id), 'embedding_vector': [[0.1] * CLIP_DIM]}

    response = store(test_client, auth_token, doc)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'not both' in error(response)


# --- the knowledge base type decides what can be stored ----------------------


@pytest.mark.asyncio
async def test_image_document_into_text_kb_is_rejected(
    seeded, test_client, auth_token, test_session
):
    kb_id = await create_kb(test_session, 'text')
    doc_id = await create_doc(test_session, kb_id)

    response = store(test_client, auth_token, image_doc(kb_id, doc_id))

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'only be stored in an image knowledge base' in error(response)
    assert await stored_doc_ids(test_session, doc_id) == []


@pytest.mark.asyncio
async def test_text_document_into_image_kb_is_rejected(
    seeded, test_client, auth_token, test_session
):
    kb_id = await create_kb(test_session, 'image')
    doc_id = await create_doc(test_session, kb_id)

    response = store(test_client, auth_token, bge_doc(kb_id, doc_id))

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'only be stored in a text knowledge base' in error(response)
    assert await stored_doc_ids(test_session, doc_id) == []


# --- image documents ---------------------------------------------------------


@pytest.mark.asyncio
async def test_image_document_into_image_kb_is_stored(
    seeded, test_client, auth_token, test_session
):
    kb_id = await create_kb(test_session, 'image')
    doc_id = await create_doc(test_session, kb_id)

    response = store(test_client, auth_token, image_doc(kb_id, doc_id, chunks=2))

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['data']['rejected'] == []
    assert await stored_doc_ids(test_session, doc_id) == [str(doc_id)] * 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'doc_kwargs',
    [
        {'clip_dim': 3},
        {'dino_dim': 3},
        # embedding_vector_1 omitted: its [[]] default used to be indexed per
        # chunk, raising IndexError from the second chunk on
        {'chunks': 3, 'dino': False},
    ],
)
async def test_invalid_image_documents_are_rejected(
    seeded, test_client, auth_token, test_session, doc_kwargs
):
    kb_id = await create_kb(test_session, 'image')
    doc_id = await create_doc(test_session, kb_id)

    response = store(test_client, auth_token, image_doc(kb_id, doc_id, **doc_kwargs))

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert 'vector size' in error(response)


# --- text (BGE-M3) documents -------------------------------------------------


@pytest.mark.asyncio
async def test_text_document_is_stored_in_the_text_columns(
    seeded, test_client, auth_token, test_session
):
    kb_id = await create_kb(test_session, 'text')
    doc_id = await create_doc(test_session, kb_id)

    response = store(test_client, auth_token, bge_doc(kb_id, doc_id, chunks=2))

    assert response.status_code == status.HTTP_200_OK
    assert response.json()['data']['rejected'] == []
    rows = await stored_text_rows(test_session, doc_id)
    assert [row.chunk_index for row in rows] == [0, 1]
    for row in rows:
        assert row.text_embedding is not None
        assert row.text_sparse_embedding is not None
        assert row.embedding_vector is None


@pytest.mark.asyncio
async def test_text_document_with_empty_sparse_vector_stores_null_sparse(
    seeded, test_client, auth_token, test_session
):
    kb_id = await create_kb(test_session, 'text')
    doc_id = await create_doc(test_session, kb_id)

    response = store(
        test_client,
        auth_token,
        bge_doc(kb_id, doc_id, sparse=[{'indices': [], 'values': []}]),
    )

    assert response.status_code == status.HTTP_200_OK
    [row] = await stored_text_rows(test_session, doc_id)
    assert row.text_embedding is not None and row.text_sparse_embedding is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('doc_kwargs', 'reason_fragment'),
    [
        ({'dense_dim': 512}, 'vector size'),
        ({'sparse': [{'indices': [1, 2], 'values': [0.5]}]}, 'same length'),
        ({'sparse': [{'indices': [250002], 'values': [0.5]}]}, 'unique token ids'),
        ({'sparse': [{'indices': [3, 3], 'values': [0.5, 0.4]}]}, 'unique token ids'),
        (
            {'sparse': [{'indices': list(range(1001)), 'values': [0.1] * 1001}]},
            'at most 1000',
        ),
        (
            {'chunks': 2, 'sparse': [{'indices': [1], 'values': [0.5]}]},
            'one entry per chunk',
        ),
    ],
)
async def test_invalid_text_documents_are_rejected(
    seeded, test_client, auth_token, test_session, doc_kwargs, reason_fragment
):
    kb_id = await create_kb(test_session, 'text')
    doc_id = await create_doc(test_session, kb_id)

    response = store(test_client, auth_token, bge_doc(kb_id, doc_id, **doc_kwargs))

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert reason_fragment in error(response)
    assert await stored_doc_ids(test_session, doc_id) == []
