from uuid import uuid4
from db_repo_module.models.session import Session
from db_repo_module.models.user import User
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
async def test_create_knowledge_base(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    new_kb_payload = {
        'name': 'Test Knowledge Base',
        'description': 'This is a test knowledge base',
        'type': 'document',
        'vector_size': 1536,
    }

    response = test_client.post(
        '/floware/v1/knowledge-bases',
        headers={'Authorization': f'Bearer {auth_token}'},
        json=new_kb_payload,
    )
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data['data']['message'] == 'Created the knowledge base successfully'


@pytest.mark.asyncio
async def test_create_knowledge_base_already_exists(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a knowledge base first
    new_kb_payload = {
        'name': 'Existing Knowledge Base',
        'description': 'This is an existing knowledge base',
        'type': 'document',
        'vector_size': 1536,
    }
    response = test_client.post(
        '/floware/v1/knowledge-bases',
        headers={'Authorization': f'Bearer {auth_token}'},
        json=new_kb_payload,
    )
    assert response.status_code == status.HTTP_200_OK

    # Try to create another knowledge base with the same name
    response = test_client.post(
        '/floware/v1/knowledge-bases',
        headers={'Authorization': f'Bearer {auth_token}'},
        json=new_kb_payload,
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    response_data = response.json()
    assert (
        response_data['meta']['error']
        == 'Knowledge Base with the same name already exists'
    )


@pytest.mark.asyncio
async def test_get_knowledge_base_by_id(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a knowledge base first
    new_kb_payload = {
        'name': 'Knowledge Base to Retrieve',
        'description': 'This is a knowledge base to retrieve',
        'type': 'document',
        'vector_size': 1536,
    }
    create_response = test_client.post(
        '/floware/v1/knowledge-bases',
        headers={'Authorization': f'Bearer {auth_token}'},
        json=new_kb_payload,
    )
    assert create_response.status_code == status.HTTP_200_OK
    created_kb_id = create_response.json()['data']['knowledge_base_id']

    # Retrieve the knowledge base by ID
    get_response = test_client.get(
        f'/floware/v1/knowledge-bases/{created_kb_id}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert get_response.status_code == status.HTTP_200_OK
    retrieved_kb = get_response.json()
    assert retrieved_kb['id'] == created_kb_id
    assert retrieved_kb['name'] == new_kb_payload['name']
    assert retrieved_kb['description'] == new_kb_payload['description']
    assert retrieved_kb['type'] == new_kb_payload['type']


@pytest.mark.asyncio
async def test_get_knowledge_base_by_non_existent_id(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    non_existent_id = str(uuid4())
    get_response = test_client.get(
        f'/floware/v1/knowledge-bases/{non_existent_id}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert get_response.status_code == status.HTTP_400_BAD_REQUEST
    assert (
        get_response.json()['detail']
        == "Knowledge Base with the mentioned id doesn't exist"
    )


@pytest.mark.asyncio
async def test_get_all_knowledge_bases_default_pagination(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a few knowledge bases
    for i in range(3):
        new_kb_payload = {
            'name': f'Knowledge Base {i}',
            'description': f'Description {i}',
            'type': 'document',
            'vector_size': 1536,
        }
        create_response = test_client.post(
            '/floware/v1/knowledge-bases',
            headers={'Authorization': f'Bearer {auth_token}'},
            json=new_kb_payload,
        )
        assert create_response.status_code == status.HTTP_200_OK

    # Retrieve all knowledge bases with default pagination
    get_response = test_client.get(
        '/floware/v1/knowledge-bases',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert get_response.status_code == status.HTTP_200_OK
    response_data = get_response.json()
    assert len(response_data['data']['resources']) == 3
    assert response_data['data']['resources'][0]['name'] == 'Knowledge Base 0'


@pytest.mark.asyncio
async def test_get_all_knowledge_bases_custom_pagination(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create more knowledge bases than the limit
    for i in range(2):
        new_kb_payload = {
            'name': f'Paginatable Knowledge Base {i}',
            'description': f'Description {i}',
            'type': 'document',
            'vector_size': 1536,
        }
        create_response = test_client.post(
            '/floware/v1/knowledge-bases',
            headers={'Authorization': f'Bearer {auth_token}'},
            json=new_kb_payload,
        )
        assert create_response.status_code == status.HTTP_200_OK

    # Retrieve with offset and limit
    get_response = test_client.get(
        '/floware/v1/knowledge-bases?offset=1&limit=2',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert get_response.status_code == status.HTTP_200_OK
    response_data = get_response.json()
    assert len(response_data['data']['resources']) == 1
    assert (
        response_data['data']['resources'][0]['name'] == 'Paginatable Knowledge Base 1'
    )


@pytest.mark.asyncio
async def test_get_all_knowledge_bases_no_exist(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Retrieve all knowledge bases when none exist
    get_response = test_client.get(
        '/floware/v1/knowledge-bases',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert get_response.status_code == status.HTTP_200_OK
    response_data = get_response.json()
    assert len(response_data['data']['resources']) == 0


@pytest.mark.asyncio
async def test_update_existing_knowledge_base(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a knowledge base first
    new_kb_payload = {
        'name': 'Knowledge Base to Update',
        'description': 'Original description',
        'type': 'document',
        'vector_size': 1536,
    }
    create_response = test_client.post(
        '/floware/v1/knowledge-bases',
        headers={'Authorization': f'Bearer {auth_token}'},
        json=new_kb_payload,
    )
    assert create_response.status_code == status.HTTP_200_OK
    created_kb_id = create_response.json()['data']['knowledge_base_id']

    # Update the knowledge base
    updated_kb_payload = {
        'name': 'Updated Knowledge Base Name',
        'description': 'Updated description',
        'type': 'image',
        'vector_size': 768,
    }
    update_response = test_client.put(
        f'/floware/v1/knowledge-bases/{created_kb_id}',
        headers={'Authorization': f'Bearer {auth_token}'},
        json=updated_kb_payload,
    )

    assert update_response.status_code == status.HTTP_200_OK
    response_data = update_response.json()
    assert response_data['data']['message'] == 'Updated the Knowledge Base successfully'
    assert response_data['data']['knowledge_base_id'] == created_kb_id

    # Verify the update by retrieving the knowledge base
    get_response = test_client.get(
        f'/floware/v1/knowledge-bases/{created_kb_id}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert get_response.status_code == status.HTTP_200_OK
    retrieved_kb = get_response.json()
    assert retrieved_kb['name'] == updated_kb_payload['name']
    assert retrieved_kb['description'] == updated_kb_payload['description']
    assert retrieved_kb['type'] == updated_kb_payload['type']


@pytest.mark.asyncio
async def test_update_non_existent_knowledge_base(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    non_existent_id = str(uuid4())
    updated_kb_payload = {
        'name': 'Non Existent KB',
        'description': 'Description',
        'type': 'document',
        'vector_size': 1536,
    }
    update_response = test_client.put(
        f'/floware/v1/knowledge-bases/{non_existent_id}',
        headers={'Authorization': f'Bearer {auth_token}'},
        json=updated_kb_payload,
    )

    assert update_response.status_code == status.HTTP_400_BAD_REQUEST
    assert (
        update_response.json()['meta']['error']
        == "Knowledge Base with the given id doesn't exist"
    )


@pytest.mark.asyncio
async def test_delete_existing_knowledge_base(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    # Create a knowledge base first
    new_kb_payload = {
        'name': 'Knowledge Base to Delete',
        'description': 'Description',
        'type': 'document',
        'vector_size': 1536,
    }
    create_response = test_client.post(
        '/floware/v1/knowledge-bases',
        headers={'Authorization': f'Bearer {auth_token}'},
        json=new_kb_payload,
    )
    assert create_response.status_code == status.HTTP_200_OK
    created_kb_id = create_response.json()['data']['knowledge_base_id']

    # Delete the knowledge base
    delete_response = test_client.delete(
        f'/floware/v1/knowledge-bases/{created_kb_id}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert delete_response.status_code == status.HTTP_204_NO_CONTENT
    response_data = delete_response.json()
    assert response_data['data']['message'] == 'Deleted the Knowledge Base successfully'
    assert response_data['data']['knowledge_base_id'] == created_kb_id

    # Verify deletion by trying to retrieve it
    get_response = test_client.get(
        f'/floware/v1/knowledge-bases/{created_kb_id}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert get_response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_delete_non_existent_knowledge_base(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
    await create_session(test_session, test_user_id, test_session_id)

    non_existent_id = str(uuid4())
    delete_response = test_client.delete(
        f'/floware/v1/knowledge-bases/{non_existent_id}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert delete_response.status_code == status.HTTP_400_BAD_REQUEST
    assert (
        delete_response.json()['meta']['error']
        == "Knowledge Base with the given id doesn't exist"
    )
