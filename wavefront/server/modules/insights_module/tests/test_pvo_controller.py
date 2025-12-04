from db_repo_module.models.resource import Resource
from db_repo_module.models.resource import ResourceScope
from db_repo_module.models.role import Role
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.models.session import Session
from db_repo_module.models.user import User
from db_repo_module.models.user_role import UserRole
import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def create_test_resources_and_roles(test_session: AsyncSession, test_user_id):
    async with test_session() as session:
        # Create and commit role first
        role = Role(
            id='test_role_id', name='test_role', description='Test role for PDO access'
        )
        session.add(role)
        await session.commit()

        # Create and commit resource
        resource = Resource(
            id='test_resource_id',
            key='test_resource',
            value='test_value',
            scope=ResourceScope.DATA,
        )
        session.add(resource)
        await session.commit()

        # Create role-resource mapping
        role_resource = RoleResource(
            role_id='test_role_id', resource_id='test_resource_id'
        )
        session.add(role_resource)

        # Create user-role mapping
        user_role = UserRole(user_id=test_user_id, role_id='test_role_id')
        session.add(user_role)
        await session.commit()


@pytest.mark.asyncio
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
async def test_get_pvo_records(
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    test_client,
    auth_token,
    mocking_pdo_controller_is_admin,
):
    await create_session(test_session, test_user_id, test_session_id)
    response = test_client.get(
        '/floware/v1/insights/parsed_data_object',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    assert len(response.json()['data']['records']) == 2


@pytest.mark.asyncio
async def test_get_pvo_record_with_empty_result(
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    test_client,
    auth_token,
    mocking_pdo_controller_is_admin,
    mock_pvo_repository_emptydata,
):
    await create_session(test_session, test_user_id, test_session_id)
    response = test_client.get(
        '/floware/v1/insights/parsed_data_object',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    assert len(response.json()['data']['records']) == 0


@pytest.mark.asyncio
async def test_get_pvo_records_without_admin_without_data_filter(
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    test_client,
    auth_token,
    mocking_pdo_controller_not_admin,
):
    await create_session(test_session, test_user_id, test_session_id)
    response = test_client.get(
        '/floware/v1/insights/parsed_data_object',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_pvo_record_without_admin_and_data_filter(
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    test_client,
    auth_token,
    mocking_pdo_controller_not_admin,
):
    await create_session(test_session, test_user_id, test_session_id)
    await create_test_resources_and_roles(test_session, test_user_id)

    response = test_client.get(
        '/floware/v1/insights/parsed_data_object',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    assert len(response.json()['data']['records']) == 2


@pytest.mark.asyncio
async def test_get_pvo_records_with_pagination(
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    test_client,
    auth_token,
    mocking_pdo_controller_is_admin,
):
    """Test getting PDO records with pagination parameters"""
    await create_session(test_session, test_user_id, test_session_id)
    await create_test_resources_and_roles(test_session, test_user_id)
    response = test_client.get(
        '/floware/v1/insights/parsed_data_object?limit=1&offset=1',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    assert (
        len(response.json()['data']['records']) == 2
    )  # bcz the fucntion always return 2 records


@pytest.mark.asyncio
async def test_get_pvo_records_with_filter(
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    test_client,
    auth_token,
    mocking_pdo_controller_is_admin,
):
    """Test getting PDO records with filter parameter"""
    await create_session(test_session, test_user_id, test_session_id)
    await create_test_resources_and_roles(test_session, test_user_id)
    response = test_client.get(
        '/floware/v1/insights/parsed_data_object?$filter=conversation_id eq conv',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_pvo_audio(
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    test_client,
    auth_token,
    mocking_pdo_controller_is_admin,
):
    """Test getting audio URL for a PDO record"""
    await create_session(test_session, test_user_id, test_session_id)
    response = test_client.get(
        '/floware/v1/insights/parsed_data_object/audio?resource_url=test_audio.mp3',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    assert 'audio_url' in response.json()['data']
    assert response.json()['data']['audio_url'] is not None


@pytest.mark.asyncio
async def test_get_pvo_audio_without_auth(
    test_session: AsyncSession, test_user_id, test_session_id, test_client
):
    """Test getting audio URL without authentication"""
    await create_session(test_session, test_user_id, test_session_id)
    response = test_client.get(
        '/floware/v1/insights/parsed_data_object/audio?resource_url=test_audio.mp3'
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_pvo_audio_without_resource_url(
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    test_client,
    auth_token,
    mocking_pdo_controller_is_admin,
):
    """Test getting audio URL without providing resource_url parameter"""
    await create_session(test_session, test_user_id, test_session_id)
    response = test_client.get(
        '/floware/v1/insights/parsed_data_object/audio',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 422  # FastAPI validation error


@pytest.mark.asyncio
async def test_get_pvo_transcript(
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    test_client,
    auth_token,
    mocking_pdo_controller_is_admin,
):
    """Test getting transcript for a PDO record"""
    await create_session(test_session, test_user_id, test_session_id)
    response = test_client.get(
        '/floware/v1/insights/parsed_data_object/transcript?resource_url=test_transcript.json',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_pvo_transcript_without_auth(
    test_session: AsyncSession, test_user_id, test_session_id, test_client
):
    """Test getting transcript without authentication"""
    await create_session(test_session, test_user_id, test_session_id)
    response = test_client.get(
        '/floware/v1/insights/parsed_data_object/transcript?resource_url=test_transcript.json'
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_pvo_transcript_without_resource_url(
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    test_client,
    auth_token,
    mocking_pdo_controller_is_admin,
):
    """Test getting transcript without providing resource_url parameter"""
    await create_session(test_session, test_user_id, test_session_id)
    response = test_client.get(
        '/floware/v1/insights/parsed_data_object/transcript',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 422  # FastAPI validation error
