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
async def test_get_roles_composite_only(
    test_client,
    test_session: AsyncSession,
    mock_auth_admin_functions,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)

    console_resource = Resource(
        id=str(uuid.uuid4()),
        key='console_resource',
        value='viewer_resource',
        description='Console resource',
        scope=ResourceScope.CONSOLE,
    )
    data_resource = Resource(
        id=str(uuid.uuid4()),
        key='branch',
        value='mumbai',
        description='Data resource',
        scope=ResourceScope.DATA,
    )
    single_resource_role = Role(
        id=str(uuid.uuid4()),
        name='single_resource_role',
        description='Role with one resource',
    )
    composite_role = Role(
        id=str(uuid.uuid4()),
        name='composite_role',
        description='Role with multiple resources',
    )

    async with test_session() as session:
        session.add_all(
            [console_resource, data_resource, single_resource_role, composite_role]
        )
        await session.commit()

    async with test_session() as session:
        session.add_all(
            [
                RoleResource(
                    role_id=single_resource_role.id,
                    resource_id=console_resource.id,
                ),
                RoleResource(
                    role_id=composite_role.id,
                    resource_id=console_resource.id,
                ),
                RoleResource(
                    role_id=composite_role.id,
                    resource_id=data_resource.id,
                ),
            ]
        )
        await session.commit()

    response = test_client.get(
        '/floware/v1/access/roles?composite_only=true',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    data = response.json()
    role_names = {role['name'] for role in data['data']['roles']}
    assert role_names == {'composite_role'}


@pytest.mark.asyncio
async def test_get_roles_composite_only_without_scopes(
    test_client,
    test_session: AsyncSession,
    mock_auth_admin_functions,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)

    console_resource = Resource(
        id=str(uuid.uuid4()),
        key='console_resource',
        value='viewer_resource',
        description='Console resource',
        scope=ResourceScope.CONSOLE,
    )
    route_resource = Resource(
        id=str(uuid.uuid4()),
        key='route',
        value='agents',
        description='Route resource',
        scope=ResourceScope.ROUTE,
    )
    composite_role = Role(
        id=str(uuid.uuid4()),
        name='cross_scope_composite_role',
        description='Role with resources across scopes',
    )

    async with test_session() as session:
        session.add_all([console_resource, route_resource, composite_role])
        await session.commit()

    async with test_session() as session:
        session.add_all(
            [
                RoleResource(
                    role_id=composite_role.id,
                    resource_id=console_resource.id,
                ),
                RoleResource(
                    role_id=composite_role.id,
                    resource_id=route_resource.id,
                ),
            ]
        )
        await session.commit()

    response = test_client.get(
        '/floware/v1/access/roles?composite_only=true',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    data = response.json()
    role_names = {role['name'] for role in data['data']['roles']}
    assert role_names == {'cross_scope_composite_role'}


@pytest.mark.asyncio
async def test_get_roles_composite_only_exact_scope_match(
    test_client,
    test_session: AsyncSession,
    mock_auth_admin_functions,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)

    data_resource_one = Resource(
        id=str(uuid.uuid4()),
        key='branch',
        value='mumbai',
        description='Data resource',
        scope=ResourceScope.DATA,
    )
    data_resource_two = Resource(
        id=str(uuid.uuid4()),
        key='branch',
        value='delhi',
        description='Data resource',
        scope=ResourceScope.DATA,
    )
    dashboard_resource = Resource(
        id=str(uuid.uuid4()),
        key='dashboard',
        value='sales',
        description='Dashboard resource',
        scope=ResourceScope.DASHBOARD,
        meta='{"name": "Sales", "key": "sales", "priority": "1"}',
    )

    # Composite role whose resources are all DATA scoped.
    data_only_role = Role(
        id=str(uuid.uuid4()),
        name='data_only_composite_role',
        description='Composite role with only data resources',
    )
    # Composite role spanning DATA + DASHBOARD scopes.
    data_dashboard_role = Role(
        id=str(uuid.uuid4()),
        name='data_dashboard_composite_role',
        description='Composite role with data and dashboard resources',
    )

    async with test_session() as session:
        session.add_all(
            [
                data_resource_one,
                data_resource_two,
                dashboard_resource,
                data_only_role,
                data_dashboard_role,
            ]
        )
        await session.commit()

    async with test_session() as session:
        session.add_all(
            [
                RoleResource(
                    role_id=data_only_role.id,
                    resource_id=data_resource_one.id,
                ),
                RoleResource(
                    role_id=data_only_role.id,
                    resource_id=data_resource_two.id,
                ),
                RoleResource(
                    role_id=data_dashboard_role.id,
                    resource_id=data_resource_one.id,
                ),
                RoleResource(
                    role_id=data_dashboard_role.id,
                    resource_id=dashboard_resource.id,
                ),
            ]
        )
        await session.commit()

    # Only DATA requested -> only the data-only composite role matches.
    response = test_client.get(
        '/floware/v1/access/roles?composite_only=true&scopes=data',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    role_names = {role['name'] for role in response.json()['data']['roles']}
    assert role_names == {'data_only_composite_role'}

    # DATA + DASHBOARD requested -> only the role spanning exactly both matches.
    response = test_client.get(
        '/floware/v1/access/roles?composite_only=true&scopes=data&scopes=dashboard',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    role_names = {role['name'] for role in response.json()['data']['roles']}
    assert role_names == {'data_dashboard_composite_role'}

    # ROUTE requested -> no composite role has only route resources.
    response = test_client.get(
        '/floware/v1/access/roles?composite_only=true&scopes=route',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    assert response.json()['data']['roles'] == []


@pytest.mark.asyncio
async def test_get_roles_scope_filter_excludes_cross_scope_composite(
    test_client,
    test_session: AsyncSession,
    mock_auth_admin_functions,
    test_user_id,
    test_session_id,
    auth_token,
):
    """Without composite_only, a scope filter still returns single-resource roles
    in that scope, but a composite role spanning multiple scopes is excluded."""
    await create_session(test_session, test_user_id, test_session_id)

    route_resource = Resource(
        id=str(uuid.uuid4()),
        key='route',
        value='agents',
        description='Route resource',
        scope=ResourceScope.ROUTE,
    )
    data_resource = Resource(
        id=str(uuid.uuid4()),
        key='branch',
        value='mumbai',
        description='Data resource',
        scope=ResourceScope.DATA,
    )
    dashboard_resource = Resource(
        id=str(uuid.uuid4()),
        key='dashboard',
        value='sales',
        description='Dashboard resource',
        scope=ResourceScope.DASHBOARD,
        meta='{"name": "Sales", "key": "sales", "priority": "1"}',
    )

    # Single-resource route role -> should appear under scopes=route.
    route_only_role = Role(
        id=str(uuid.uuid4()),
        name='route_only_role',
        description='Single route resource role',
    )
    # Composite role spanning route + data + dashboard -> should NOT appear
    # under scopes=route.
    cross_scope_role = Role(
        id=str(uuid.uuid4()),
        name='cross_scope_role',
        description='Composite role spanning multiple scopes',
    )

    async with test_session() as session:
        session.add_all(
            [
                route_resource,
                data_resource,
                dashboard_resource,
                route_only_role,
                cross_scope_role,
            ]
        )
        await session.commit()

    async with test_session() as session:
        session.add_all(
            [
                RoleResource(role_id=route_only_role.id, resource_id=route_resource.id),
                RoleResource(
                    role_id=cross_scope_role.id, resource_id=route_resource.id
                ),
                RoleResource(role_id=cross_scope_role.id, resource_id=data_resource.id),
                RoleResource(
                    role_id=cross_scope_role.id, resource_id=dashboard_resource.id
                ),
            ]
        )
        await session.commit()

    response = test_client.get(
        '/floware/v1/access/roles?scopes=route',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    role_names = {role['name'] for role in response.json()['data']['roles']}
    assert role_names == {'route_only_role'}


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
