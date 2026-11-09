"""Image uploads to a knowledge base are size-checked before anything is
stored or queued.

The ingestion worker sends every uploaded image to the inference service,
which decodes all of its pixels, so a small file declaring huge dimensions
would exhaust the service's memory at indexing time.
"""

from uuid import uuid4

import pytest
from common_module.utils.image_formats import MAX_IMAGE_BYTES
from db_repo_module.models.knowledge_base_documents import KnowledgeBaseDocuments
from db_repo_module.models.knowledge_bases import KnowledgeBase
from fastapi import status
from flo_testing import seed_user_session as create_session
from kb_image_fixtures import jpeg_bytes
from knowledge_base_module.image_validation import (
    IMAGE_TOO_LARGE_MESSAGE,
    IMAGE_TOO_MANY_PIXELS_MESSAGE,
    UNSUPPORTED_IMAGE_MESSAGE,
)
from sqlalchemy import select


@pytest.fixture
async def image_kb(test_session, test_user_id, test_session_id):
    await create_session(test_session, test_user_id, test_session_id)
    kb_id = uuid4()
    async with test_session() as session:
        session.add(
            KnowledgeBase(
                id=kb_id,
                name=f'Upload limits KB {kb_id}',
                description='',
                type='image',
                vector_size=512,
                vector_size_1=1024,
            )
        )
        await session.commit()
    return kb_id


def _upload(test_client, auth_token, kb_id, content, content_type='image/jpeg'):
    return test_client.post(
        f'/floware/v1/knowledge-bases/{kb_id}/documents',
        headers={'Authorization': f'Bearer {auth_token}'},
        files={'file': ('photo.jpg', content, content_type)},
    )


async def _document_count(test_session, kb_id) -> int:
    async with test_session() as session:
        rows = await session.scalars(
            select(KnowledgeBaseDocuments).where(
                KnowledgeBaseDocuments.knowledge_base_id == kb_id
            )
        )
        return len(rows.all())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('content', 'expected_error'),
    [
        # The finding: 100 MP, small on the wire.
        (jpeg_bytes(10_000, 10_000), IMAGE_TOO_MANY_PIXELS_MESSAGE),
        (jpeg_bytes(8_000, 5_001), IMAGE_TOO_MANY_PIXELS_MESSAGE),
        (jpeg_bytes(20_000, 20_000), IMAGE_TOO_MANY_PIXELS_MESSAGE),
        (b'plain text with an image content type', UNSUPPORTED_IMAGE_MESSAGE),
        (b'\xff' * (MAX_IMAGE_BYTES + 1), IMAGE_TOO_LARGE_MESSAGE),
    ],
    ids=['100mp', 'just-over-limit', 'pillow-bomb', 'not-image', 'too-big'],
)
async def test_rejected_images_are_not_stored_or_queued(
    test_client,
    auth_token,
    test_session,
    setup_containers,
    image_kb,
    content,
    expected_error,
):
    kb_container = setup_containers[3]

    response = _upload(test_client, auth_token, image_kb, content)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()['meta']['error'] == expected_error
    assert await _document_count(test_session, image_kb) == 0
    kb_container.cloud_storage_manager().save_small_file.assert_not_called()
    kb_container.message_queue().add_message.assert_not_called()


@pytest.mark.asyncio
async def test_image_at_the_pixel_limit_is_accepted(
    test_client, auth_token, test_session, setup_containers, image_kb
):
    content = jpeg_bytes(8_000, 5_000)

    response = _upload(test_client, auth_token, image_kb, content)

    assert response.status_code == status.HTTP_200_OK
    assert await _document_count(test_session, image_kb) == 1
    saved = setup_containers[3].cloud_storage_manager().save_small_file.call_args
    assert saved.kwargs['file_content'] == content
    setup_containers[3].message_queue().add_message.assert_called_once()
