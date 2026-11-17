"""The retrieve API rejects oversized images before calling inference.

Reproduces the security finding: a small JPEG declaring 10,000 x 10,000
pixels (100 MP) exhausted the inference service's memory when decoded.
"""

import base64
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_module.utils.image_formats import MAX_IMAGE_BYTES
from db_repo_module.models.knowledge_bases import KnowledgeBase
from dependency_injector import providers
from fastapi import status
from flo_testing import seed_user_session as create_session
from kb_image_fixtures import jpeg_base64, jpeg_bytes
from knowledge_base_module.image_validation import (
    IMAGE_TOO_LARGE_MESSAGE,
    IMAGE_TOO_MANY_PIXELS_MESSAGE,
    INVALID_BASE64_MESSAGE,
    UNSUPPORTED_IMAGE_MESSAGE,
    validate_image_bytes,
)


async def _image_kb(test_session, test_user_id, test_session_id):
    await create_session(test_session, test_user_id, test_session_id)
    kb_id = uuid4()
    async with test_session() as session:
        session.add(
            KnowledgeBase(
                id=kb_id,
                name=f'Image limits KB {kb_id}',
                description='',
                type='image',
                vector_size=512,
                vector_size_1=1024,
            )
        )
        await session.commit()
    return kb_id


def _mock_image_retrieval(kb_container):
    image = AsyncMock()
    image.retrieve_images.return_value = [{'doc': 'image doc'}]
    kb_container.image_knowledge_base_retrieve.override(
        providers.Singleton(lambda: image)
    )
    return image


@pytest.fixture
async def image_kb(test_session, test_user_id, test_session_id):
    return await _image_kb(test_session, test_user_id, test_session_id)


def _retrieve(test_client, auth_token, kb_id, body):
    return test_client.post(
        f'/floware/v1/knowledge-base/{kb_id}/retrieve',
        headers={'Authorization': f'Bearer {auth_token}'},
        json=body,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('image_data', 'expected_error'),
    [
        # The finding: 100 MP, small on the wire.
        (jpeg_base64(10_000, 10_000), IMAGE_TOO_MANY_PIXELS_MESSAGE),
        # Just over the 40 MP limit.
        (jpeg_base64(8_000, 5_001), IMAGE_TOO_MANY_PIXELS_MESSAGE),
        # Past Pillow's own refusal threshold (~179 MP).
        (jpeg_base64(20_000, 20_000), IMAGE_TOO_MANY_PIXELS_MESSAGE),
        ('not-base64!!', INVALID_BASE64_MESSAGE),
        (
            base64.b64encode(b'plain text, not an image').decode(),
            UNSUPPORTED_IMAGE_MESSAGE,
        ),
        ('A' * (MAX_IMAGE_BYTES * 2), IMAGE_TOO_LARGE_MESSAGE),
    ],
    ids=[
        '100mp',
        'just-over-limit',
        'pillow-bomb',
        'bad-base64',
        'not-image',
        'too-big',
    ],
)
async def test_rejected_image_data_never_reaches_inference(
    test_client, auth_token, setup_containers, image_kb, image_data, expected_error
):
    image = _mock_image_retrieval(setup_containers[3])

    response = _retrieve(test_client, auth_token, image_kb, {'image_data': image_data})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()['meta']['error'] == expected_error
    image.retrieve_images.assert_not_awaited()
    image.exact_match_dino.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'image_data',
    [
        jpeg_base64(),
        jpeg_base64(8_000, 5_000),
        f'data:image/jpeg;base64,{jpeg_base64()}',
    ],
    ids=['small', 'exactly-40mp', 'data-url'],
)
async def test_images_within_limits_are_forwarded_unchanged(
    test_client, auth_token, setup_containers, image_kb, image_data
):
    image = _mock_image_retrieval(setup_containers[3])

    response = _retrieve(test_client, auth_token, image_kb, {'image_data': image_data})

    assert response.status_code == status.HTTP_200_OK
    assert image.retrieve_images.await_args.args[0] == image_data


@pytest.mark.asyncio
async def test_oversized_image_url_is_rejected(
    test_client, auth_token, setup_containers, image_kb
):
    kb_container = setup_containers[3]
    image = _mock_image_retrieval(kb_container)
    kb_container.cloud_storage_manager().get_bucket_key.return_value = (
        'bucket',
        'bomb.jpg',
    )
    kb_container.cloud_storage_manager().read_file.return_value = jpeg_bytes(
        10_000, 10_000
    )

    response = _retrieve(
        test_client, auth_token, image_kb, {'image_url': 'gs://bucket/bomb.jpg'}
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()['meta']['error'] == IMAGE_TOO_MANY_PIXELS_MESSAGE
    image.retrieve_images.assert_not_awaited()


def test_oversized_bytes_are_rejected_before_parsing():
    with pytest.raises(ValueError, match=IMAGE_TOO_LARGE_MESSAGE):
        validate_image_bytes(b'\xff' * (MAX_IMAGE_BYTES + 1))


@pytest.mark.parametrize(
    'message', [IMAGE_TOO_LARGE_MESSAGE, IMAGE_TOO_MANY_PIXELS_MESSAGE]
)
def test_limit_errors_do_not_reveal_the_limits(message):
    # Naming a limit tells a prober exactly how large an image can be crafted.
    assert not any(char.isdigit() for char in message)
