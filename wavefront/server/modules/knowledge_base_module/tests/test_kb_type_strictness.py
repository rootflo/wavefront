"""
Knowledge base types are strict: `text` (BGE-M3; text and PDF files) or
`image` (CLIP + DINOv3; image files). The type sets the vector sizes, can't be
changed later, and decides which files can be uploaded.
"""

from uuid import uuid4

import pytest
from db_repo_module.models.knowledge_base_documents import KnowledgeBaseDocuments
from db_repo_module.models.knowledge_bases import KnowledgeBase
from fastapi import status
from flo_testing import seed_user_session as create_session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

KB_URL = '/floware/v1/knowledge-bases'


@pytest.fixture
async def seeded(test_session, test_user_id, test_session_id):
    await create_session(test_session, test_user_id, test_session_id)


def auth(token):
    return {'Authorization': f'Bearer {token}'}


def create(test_client, auth_token, kb_type, **extra):
    return test_client.post(
        KB_URL,
        headers=auth(auth_token),
        json={
            'name': f'KB {uuid4()}',
            'description': 'strict types',
            'type': kb_type,
            **extra,
        },
    )


# --- create -----------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('kb_type', 'sizes'), [('text', (1024, None)), ('image', (512, 1024))]
)
async def test_vector_sizes_are_derived_from_the_type(
    seeded, test_client, auth_token, kb_type, sizes
):
    response = create(test_client, auth_token, kb_type)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()['data']
    assert data['type'] == kb_type
    assert (data['vector_size'], data['vector_size_1']) == sizes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('kb_type', 'extra'),
    [
        ('text', {'vector_size': 1024}),
        # older clients sent 0 for "no second vector"
        ('text', {'vector_size': 1024, 'vector_size_1': 0}),
        ('image', {'vector_size': 512, 'vector_size_1': 1024}),
    ],
)
async def test_matching_vector_sizes_are_accepted(
    seeded, test_client, auth_token, kb_type, extra
):
    assert create(test_client, auth_token, kb_type, **extra).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('kb_type', 'extra', 'message'),
    [
        ('General', {}, "'text' or 'image'"),
        ('document', {}, "'text' or 'image'"),
        ('text', {'vector_size': 1536}, 'vector_size 1024'),
        ('text', {'vector_size_1': 1024}, 'have no vector_size_1'),
        ('image', {'vector_size': 1024}, 'vector_size 512'),
        ('image', {'vector_size_1': 0}, 'vector_size_1 1024'),
    ],
)
async def test_invalid_type_or_sizes_are_rejected(
    seeded, test_client, auth_token, test_session, kb_type, extra, message
):
    response = create(test_client, auth_token, kb_type, **extra)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert message in response.text
    async with test_session() as session:
        assert (await session.scalars(select(KnowledgeBase))).all() == []


@pytest.mark.asyncio
async def test_database_rejects_other_types(seeded, test_session):
    with pytest.raises(IntegrityError, match='ck_knowledge_bases_type'):
        async with test_session() as session:
            session.add(
                KnowledgeBase(
                    id=uuid4(),
                    name='bad',
                    description='',
                    type='General',
                    vector_size=1024,
                )
            )
            await session.commit()


# --- update -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_type_cannot_be_changed(seeded, test_client, auth_token):
    kb_id = create(test_client, auth_token, 'text').json()['data']['id']

    response = test_client.patch(
        f'{KB_URL}/{kb_id}', headers=auth(auth_token), json={'type': 'image'}
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "type can't be changed" in response.json()['meta']['error']
    assert (
        test_client.get(f'{KB_URL}/{kb_id}', headers=auth(auth_token)).json()['data'][
            'type'
        ]
        == 'text'
    )


@pytest.mark.asyncio
async def test_resending_the_same_type_on_update_is_fine(
    seeded, test_client, auth_token
):
    kb_id = create(test_client, auth_token, 'image').json()['data']['id']

    response = test_client.patch(
        f'{KB_URL}/{kb_id}',
        headers=auth(auth_token),
        json={'name': f'Renamed {uuid4()}', 'type': 'image'},
    )

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_update_rejects_unknown_types(seeded, test_client, auth_token):
    kb_id = create(test_client, auth_token, 'text').json()['data']['id']

    response = test_client.patch(
        f'{KB_URL}/{kb_id}', headers=auth(auth_token), json={'type': 'General'}
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


# --- upload -----------------------------------------------------------------


def upload(test_client, auth_token, kb_id, content_type, filename='file'):
    return test_client.post(
        f'{KB_URL}/{kb_id}/documents',
        headers=auth(auth_token),
        files={'file': (filename, b'content', content_type)},
    )


async def document_count(test_session, kb_id) -> int:
    async with test_session() as session:
        rows = await session.scalars(
            select(KnowledgeBaseDocuments).where(
                KnowledgeBaseDocuments.knowledge_base_id == kb_id
            )
        )
        return len(rows.all())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('kb_type', 'content_type'),
    [
        ('text', 'text/plain'),
        ('text', 'text/plain; charset=utf-8'),
        ('text', 'application/pdf'),
        ('image', 'image/png'),
        ('image', 'image/jpeg'),
        ('image', 'image/webp'),
    ],
)
async def test_files_the_type_can_index_are_accepted(
    seeded,
    test_client,
    auth_token,
    test_session,
    setup_containers,
    kb_type,
    content_type,
):
    kb_id = create(test_client, auth_token, kb_type).json()['data']['id']

    response = upload(test_client, auth_token, kb_id, content_type)

    assert response.status_code == status.HTTP_200_OK
    assert await document_count(test_session, kb_id) == 1
    setup_containers[3].message_queue().add_message.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('kb_type', 'content_type'),
    [
        ('text', 'image/png'),
        ('text', 'application/msword'),
        ('text', 'text/csv'),
        ('image', 'text/plain'),
        ('image', 'application/pdf'),
        ('image', 'image/svg+xml'),
    ],
)
async def test_files_the_type_cannot_index_are_rejected_before_storing(
    seeded,
    test_client,
    auth_token,
    test_session,
    setup_containers,
    kb_type,
    content_type,
):
    kb_id = create(test_client, auth_token, kb_type).json()['data']['id']
    kb_container = setup_containers[3]

    response = upload(test_client, auth_token, kb_id, content_type)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert f'{kb_type} knowledge bases accept' in response.json()['meta']['error']
    assert await document_count(test_session, kb_id) == 0
    kb_container.cloud_storage().save_small_file.assert_not_called()
    kb_container.message_queue().add_message.assert_not_called()
