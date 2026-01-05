import uuid

from db_repo_module.models.resource import Resource
from db_repo_module.models.resource import ResourceScope
from db_repo_module.models.role import Role
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.models.session import Session
from db_repo_module.models.user import User
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from user_management_module.models.resource import AddableResourceScope


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
async def test_create_resource(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    auth_token,
    mock_auth_admin_functions,
):
    await create_session(test_session, test_user_id, test_session_id)
    resource_payload = {
        'resources': [
            {
                'key': 'test_resource',
                'value': 'Test Resource',
                'description': 'Test Description',
                'scope': AddableResourceScope.DATA,
            }
        ]
    }
    response = test_client.post(
        '/floware/v1/access/resources',
        json=resource_payload,
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 201
    data = response.json()
    assert 'Created 1 resources successfully' in data['data']['message']

    async with test_session() as session:
        result = await session.execute(select(Resource))
        resources = result.scalars().all()
        assert len(resources) == 1
        assert resources[0].key == 'test_resource'


@pytest.mark.asyncio
async def test_create_role(
    test_client,
    test_session: AsyncSession,
    mock_auth_admin_functions,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)

    resource = Resource(
        id=str(uuid.uuid4()),
        key='test_resource',
        value='Test Resource',
        description='Test Description',
        scope=ResourceScope.DASHBOARD,
    )
    resource_id = resource.id
    async with test_session() as session:
        session.add(resource)
        await session.commit()

    role_payload = {
        'name': 'test_role',
        'description': 'Test Role Description',
        'resources': [resource_id],
    }

    response = test_client.post(
        '/floware/v1/access/roles',
        json=role_payload,
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 201
    data = response.json()
    assert 'Created role successfully' in data['data']['message']

    async with test_session() as session:
        result = await session.execute(select(Role))
        roles = result.scalars().all()
        assert len(roles) == 1
        assert roles[0].name == 'test_role'


@pytest.mark.asyncio
async def test_get_roles(
    test_client,
    test_session: AsyncSession,
    mock_auth_admin_functions,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    resource = Resource(
        id=str(uuid.uuid4()),
        key='test_resource',
        value='Test Resource',
        description='Test Description',
        scope=ResourceScope.CONSOLE,
    )
    role = Role(
        id=str(uuid.uuid4()), name='test_role', description='Test Role Description'
    )
    resource_id = resource.id
    role_id = role.id
    async with test_session() as session:
        session.add_all([resource, role])
        await session.commit()

    role_resource = RoleResource(role_id=role_id, resource_id=resource_id)
    async with test_session() as session:
        session.add(role_resource)
        await session.commit()

    response = test_client.get(
        '/floware/v1/access/roles', headers={'Authorization': f'Bearer {auth_token}'}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data['data']['roles']) == 1
    assert data['data']['roles'][0]['name'] == 'test_role'


@pytest.mark.asyncio
async def test_create_role_invalid_resources(
    test_client,
    test_session: AsyncSession,
    mock_auth_admin_functions,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    role_payload = {
        'name': 'test_role',
        'description': 'Test Role Description',
        'resources': [str(uuid.uuid4())],  # Non-existent resource ID
    }

    response = test_client.post(
        '/floware/v1/access/roles',
        json=role_payload,
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 400
    data = response.json()
    assert 'found 1 unknown resource(s) in the payload' in data['meta']['error'].lower()
