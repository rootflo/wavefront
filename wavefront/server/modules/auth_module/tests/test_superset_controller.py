import json
from uuid import uuid4

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
async def test_superset_authenticator_with_admin(
    test_client,
    auth_token,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    mock_auth_functions,
):
    role_id = str(uuid4())
    dashboard_resource_id = str(uuid4())
    data_filter_resource_id = str(uuid4())

    # Create a user in the database
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

    role = Role(id=role_id, name='test_role', description='Test Role Description')
    dashboard_resource = Resource(
        id=dashboard_resource_id,
        key='dashboard_resource',
        value='test_dashboard',
        description='Test Dashboard Resource',
        scope=ResourceScope.DASHBOARD,
    )
    data_filter_resource = Resource(
        id=data_filter_resource_id,
        key='region',
        value='North',
        description='Region filter for North region',
        scope=ResourceScope.DATA,
        meta=json.dumps(
            {'type': 'string', 'allowed_values': ['North', 'South', 'East', 'West']}
        ),
    )
    dashboard_role_resource = RoleResource(
        role_id=role_id, resource_id=dashboard_resource_id
    )
    data_filter_role_resource = RoleResource(
        role_id=role_id, resource_id=data_filter_resource_id
    )
    user_role = UserRole(user_id=test_user_id, role_id=role_id)

    async with test_session() as session:
        # First add and commit the user, session, and role
        session.add(user)
        session.add(db_session)
        session.add(role)
        await session.commit()

        # Then add and commit the resources
        session.add(dashboard_resource)
        session.add(data_filter_resource)
        await session.commit()

        # Finally add and commit the mappings
        session.add(dashboard_role_resource)
        session.add(data_filter_role_resource)
        session.add(user_role)
        await session.commit()

    response = test_client.get(
        '/v1/superset/authenticate', headers={'Authorization': f'Bearer {auth_token}'}
    )
    assert response.json()['data']['token'] == 'mock_guest_token'
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_superset_authenticator_without_admin(
    test_client,
    auth_token,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    mock_admin_false_functions,
):
    role_id = str(uuid4())
    dashboard_resource_id = str(uuid4())
    data_filter_resource_id = str(uuid4())

    # Create a user in the database
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

    role = Role(id=role_id, name='test_role', description='Test Role Description')
    dashboard_resource = Resource(
        id=dashboard_resource_id,
        key='dashboard_resource',
        value='test_dashboard',
        description='Test Dashboard Resource',
        scope=ResourceScope.DASHBOARD,
    )
    data_filter_resource = Resource(
        id=data_filter_resource_id,
        key='region',
        value='North',
        description='Region filter for North region',
        scope=ResourceScope.DATA,
        meta=json.dumps(
            {'type': 'string', 'allowed_values': ['North', 'South', 'East', 'West']}
        ),
    )
    dashboard_role_resource = RoleResource(
        role_id=role_id, resource_id=dashboard_resource_id
    )
    data_filter_role_resource = RoleResource(
        role_id=role_id, resource_id=data_filter_resource_id
    )
    user_role = UserRole(user_id=test_user_id, role_id=role_id)

    async with test_session() as session:
        # First add and commit the user, session, and role
        session.add(user)
        session.add(db_session)
        session.add(role)
        await session.commit()

        # Then add and commit the resources
        session.add(dashboard_resource)
        session.add(data_filter_resource)
        await session.commit()

        # Finally add and commit the mappings
        session.add(dashboard_role_resource)
        session.add(data_filter_role_resource)
        session.add(user_role)
        await session.commit()

    response = test_client.get(
        '/v1/superset/authenticate', headers={'Authorization': f'Bearer {auth_token}'}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_superset_authenticator_with_admin_and_dashboard_empty(
    test_client,
    auth_token,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    mock_auth_functions,
):
    role_id = str(uuid4())
    dashboard_resource_id = str(uuid4())
    data_filter_resource_id = str(uuid4())

    # Create a user in the database
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

    role = Role(id=role_id, name='test_role', description='Test Role Description')
    dashboard_resource = Resource(
        id=dashboard_resource_id,
        key='dashboard_resource',
        value='test_dashboard',
        description='Test Dashboard Resource',
        scope=ResourceScope.CONSOLE,
    )
    data_filter_resource = Resource(
        id=data_filter_resource_id,
        key='region',
        value='North',
        description='Region filter for North region',
        scope=ResourceScope.DATA,
        meta=json.dumps(
            {'type': 'string', 'allowed_values': ['North', 'South', 'East', 'West']}
        ),
    )
    dashboard_role_resource = RoleResource(
        role_id=role_id, resource_id=dashboard_resource_id
    )
    data_filter_role_resource = RoleResource(
        role_id=role_id, resource_id=data_filter_resource_id
    )
    user_role = UserRole(user_id=test_user_id, role_id=role_id)

    async with test_session() as session:
        # First add and commit the user, session, and role
        session.add(user)
        session.add(db_session)
        session.add(role)
        await session.commit()

        # Then add and commit the resources
        session.add(dashboard_resource)
        session.add(data_filter_resource)
        await session.commit()

        # Finally add and commit the mappings
        session.add(dashboard_role_resource)
        session.add(data_filter_role_resource)
        session.add(user_role)
        await session.commit()

    response = test_client.get(
        '/v1/superset/authenticate', headers={'Authorization': f'Bearer {auth_token}'}
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_superset_authenticator_not_admin_and_data_filter_empty(
    test_client,
    auth_token,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    mock_admin_false_functions,
):
    role_id = str(uuid4())
    dashboard_resource_id = str(uuid4())

    # Create a user in the database
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

    role = Role(id=role_id, name='test_role', description='Test Role Description')
    dashboard_resource = Resource(
        id=dashboard_resource_id,
        key='dashboard_resource',
        value='test_dashboard',
        description='Test Dashboard Resource',
        scope=ResourceScope.DASHBOARD,
    )
    dashboard_role_resource = RoleResource(
        role_id=role_id, resource_id=dashboard_resource_id
    )
    user_role = UserRole(user_id=test_user_id, role_id=role_id)

    async with test_session() as session:
        # First add and commit the user, session, and role
        session.add(user)
        session.add(db_session)
        session.add(role)
        await session.commit()

        # Then add and commit the resources
        session.add(dashboard_resource)
        await session.commit()

        # Finally add and commit the mappings
        session.add(dashboard_role_resource)
        session.add(user_role)
        await session.commit()

    response = test_client.get(
        '/v1/superset/authenticate', headers={'Authorization': f'Bearer {auth_token}'}
    )
    assert response.status_code == 400
