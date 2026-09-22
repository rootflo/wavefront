import uuid
from datetime import datetime, timedelta, timezone

from db_repo_module.models.resource import Resource
from db_repo_module.models.resource import ResourceScope
from db_repo_module.models.role import Role
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.models.session import Session
from db_repo_module.models.user import User
from db_repo_module.models.user_role import UserRole
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from user_management_module.utils.user_utils import get_session_cache_key
from flo_testing import seed_user_session as create_session


async def setup_role_with_console_resource(test_session: AsyncSession, role_id: str):
    async with test_session() as session:
        # Create console resource
        console_resource = Resource(
            key='console_access',
            value='true',
            description='Console access resource',
            scope=ResourceScope.CONSOLE,
        )
        session.add(console_resource)
        await session.flush()

        # Create role
        role = Role(id=role_id, name='Test Role')
        session.add(role)
        await session.flush()

        # Link role with console resource
        role_resource = RoleResource(role_id=role.id, resource_id=console_resource.id)
        session.add(role_resource)
        await session.commit()


@pytest.mark.asyncio
async def test_create_user_success(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    # Create test role with console resource
    await create_session(test_session, test_user_id, test_session_id)
    await setup_role_with_console_resource(test_session, 'test_role_id')

    new_user_data = {
        'email': 'test2@example.com',
        'password': 'Test@123',  # Updated password with special character
        'confirm_password': 'Test@123',
        'first_name': 'Test',
        'last_name': 'User',
        'role_id': ['test_role_id'],
    }

    response = test_client.post(
        '/floware/v1/users',
        json=new_user_data,
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == 200
    # checking if the user is created in the database
    async with test_session() as session:
        user = await session.execute(
            select(User).where(User.email == new_user_data['email'])
        )
        assert user is not None


@pytest.mark.asyncio
async def test_create_user_mismatched_confirmation(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    await setup_role_with_console_resource(test_session, 'test_role_id')

    new_user_data = {
        'email': 'mismatch@example.com',
        'password': 'Test@123',
        'confirm_password': 'Different@123',
        'first_name': 'Test',
        'last_name': 'User',
        'role_id': ['test_role_id'],
    }

    response = test_client.post(
        '/floware/v1/users',
        json=new_user_data,
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 422
    assert 'do not match' in str(response.json()).lower()


@pytest.mark.asyncio
async def test_send_reset_password_email_soft_deleted_user(
    test_client,
    setup_containers,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    """Soft deleted users get no reset mail, and no hint that they did not.

    The reply is byte-for-byte the one a live account gets, so the only thing
    worth asserting on is that no mail went out -- a distinguishable response
    here would turn the endpoint into an account enumeration oracle.
    """
    _, _, user_container = setup_containers
    email_service = user_container.email_send_service()
    email_service.send.reset_mock()

    # Create test user and session
    await create_session(test_session, test_user_id, test_session_id)

    # Create a soft deleted user for password reset attempt
    async with test_session() as session:
        user = User(
            email='deleted_reset@example.com',
            password='hashedpassword',
            first_name='Deleted',
            last_name='User',
            deleted=True,  # User is soft deleted
        )
        session.add(user)
        await session.commit()

    response = test_client.post(
        '/floware/v1/user/send-reset-password-email?email=deleted_reset@example.com',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    assert 'If an account exists' in response.json()['data']['message']
    email_service.send.assert_not_called()


@pytest.mark.asyncio
async def test_send_reset_password_email_unknown_email(
    test_client,
    setup_containers,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    """An address with no account behind it is answered exactly like one that has."""
    _, _, user_container = setup_containers
    email_service = user_container.email_send_service()
    email_service.send.reset_mock()

    await create_session(test_session, test_user_id, test_session_id)

    response = test_client.post(
        '/floware/v1/user/send-reset-password-email?email=nobody@example.com',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    assert 'If an account exists' in response.json()['data']['message']
    email_service.send.assert_not_called()


@pytest.mark.asyncio
async def test_send_reset_password_email_locked_user(
    test_client,
    setup_containers,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    """A locked account is not told it is locked.

    Lockout details can only ever be produced for an address that does resolve
    to a user, so returning them would leak the very fact the generic message
    exists to hide. The login endpoint is where a locked user learns about it.
    """
    _, _, user_container = setup_containers
    email_service = user_container.email_send_service()
    email_service.send.reset_mock()

    await create_session(test_session, test_user_id, test_session_id)

    async with test_session() as session:
        user = User(
            email='locked_reset@example.com',
            password='hashedpassword',
            first_name='Locked',
            last_name='User',
            failed_attempts=3,
            locked_until=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        session.add(user)
        await session.commit()

    response = test_client.post(
        '/floware/v1/user/send-reset-password-email?email=locked_reset@example.com',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    assert 'If an account exists' in response.json()['data']['message']
    assert 'locked' not in response.text.lower()
    email_service.send.assert_not_called()


@pytest.mark.asyncio
async def test_create_user_duplicate_email(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    # Create existing user
    async with test_session() as session:
        user = User(
            email='existing@example.com',
            password='hashedpassword',
            first_name='Existing',
            last_name='User',
        )
        session.add(user)
        await session.commit()

    new_user_data = {
        'email': 'existing@example.com',
        'password': 'Test@123',
        'confirm_password': 'Test@123',
        'first_name': 'Test',
        'last_name': 'User',
        'role_id': ['test_role_id'],
    }

    response = test_client.post(
        '/floware/v1/users',
        json=new_user_data,
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_update_user_success(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    # Create test user and role
    async with test_session() as session:
        user = User(
            email='update_test@example.com',  # Changed email to avoid conflict
            password='hashedpassword',
            first_name='Test',
            last_name='User',
        )
        session.add(user)
        await session.flush()
        user_id = str(user.id)  # Get the ID before committing

        role = Role(id='new_role_id', name='New Role')
        session.add(role)
        await session.commit()

    update_data = {
        'user_id': user_id,  # Use the stored ID
        'add_role_ids': ['new_role_id'],
        # Omit delete_role_ids since it's optional and we don't want to delete any roles
    }

    response = test_client.patch(
        '/floware/v1/users',
        json=update_data,
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200

    # Verify the role assignment in the database
    async with test_session() as session:
        user_roles = await session.execute(
            select(UserRole).where(UserRole.user_id == user_id)
        )
        user_roles = user_roles.scalars().all()
        assert len(user_roles) == 1
        assert user_roles[0].role_id == 'new_role_id'


@pytest.mark.asyncio
async def test_update_user_password_requires_matching_confirmation(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    async with test_session() as session:
        user = User(
            email='update_pw@example.com',
            password='hashedpassword',
            first_name='Test',
            last_name='User',
        )
        session.add(user)
        await session.flush()
        user_id = str(user.id)
        await session.commit()

    response = test_client.patch(
        '/floware/v1/users',
        json={
            'user_id': user_id,
            'password': 'Test@123',
            'confirm_password': 'Test@123',
        },
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_update_user_password_mismatched_confirmation(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    async with test_session() as session:
        user = User(
            email='update_pw_mismatch@example.com',
            password='hashedpassword',
            first_name='Test',
            last_name='User',
        )
        session.add(user)
        await session.flush()
        user_id = str(user.id)
        await session.commit()

    response = test_client.patch(
        '/floware/v1/users',
        json={
            'user_id': user_id,
            'password': 'Test@123',
            'confirm_password': 'Different@123',
        },
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 422
    assert 'do not match' in str(response.json()).lower()


@pytest.mark.asyncio
async def test_get_all_users(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    # Create test users
    async with test_session() as session:
        user1 = User(
            email='user1@example.com',
            password='hashedpassword',
            first_name='User',
            last_name='One',
        )
        user2 = User(
            email='user2@example.com',
            password='hashedpassword',
            first_name='User',
            last_name='Two',
        )
        session.add_all([user1, user2])
        await session.commit()

    response = test_client.get(
        '/floware/v1/users', headers={'Authorization': f'Bearer {auth_token}'}
    )
    assert response.status_code == 200
    assert len(response.json()['data']['users']) >= 2


async def _seed_listing_users(test_session):
    """Two extra users so a listing has something to return beyond the caller."""
    async with test_session() as session:
        session.add_all(
            [
                User(
                    email='user1@example.com',
                    password='hashedpassword',
                    first_name='User',
                    last_name='One',
                ),
                User(
                    email='user2@example.com',
                    password='hashedpassword',
                    first_name='User',
                    last_name='Two',
                ),
            ]
        )
        await session.commit()


# force_fetch=1 on every listing call below is load-bearing, not incidental. The
# shared cache_manager mock returns a truthy session blob for *any* key, so a
# cached read would short-circuit the endpoint and the assertions would be made
# against the mock rather than against the query under test.


@pytest.mark.asyncio
async def test_get_all_users_non_admin_with_flag_omits_roles(
    test_client,
    mock_auth_non_admin_user_functions,
    set_non_admin_data_access_flag,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    """A non-admin gets id/name/email only — no roles, groups or username."""
    set_non_admin_data_access_flag(True)
    await create_session(test_session, test_user_id, test_session_id)
    await _seed_listing_users(test_session)

    response = test_client.get(
        '/floware/v1/users?force_fetch=1',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == 200
    users = response.json()['data']['users']
    assert len(users) >= 2
    for user in users:
        assert set(user.keys()) == {'id', 'first_name', 'last_name', 'email'}
        assert 'roles' not in user
        assert 'groups' not in user
        assert 'username' not in user


@pytest.mark.asyncio
async def test_get_all_users_non_admin_cannot_filter_by_role(
    test_client,
    mock_auth_non_admin_user_functions,
    set_non_admin_data_access_flag,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    """The role filter is refused: the filtered set would itself disclose roles.

    Withholding the roles field is pointless if `?roles=admin` still returns
    exactly the admins, so the parameter is rejected rather than ignored.
    """
    set_non_admin_data_access_flag(True)
    await create_session(test_session, test_user_id, test_session_id)

    response = test_client.get(
        '/floware/v1/users?roles=admin&force_fetch=1',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == 403
    assert 'admin access' in response.json()['meta']['error']


@pytest.mark.asyncio
async def test_get_all_users_non_admin_without_flag_denied(
    test_client,
    mock_auth_non_admin_user_functions,
    set_non_admin_data_access_flag,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    """With the flag off the listing stays admin-only."""
    set_non_admin_data_access_flag(False)
    await create_session(test_session, test_user_id, test_session_id)
    await _seed_listing_users(test_session)

    response = test_client.get(
        '/floware/v1/users?force_fetch=1',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == 401
    # `data` is present but null on an error response, so no listing leaks
    # through the denial.
    assert response.json()['data'] is None
    assert 'Access denied' in response.json()['meta']['error']


@pytest.mark.asyncio
async def test_get_all_users_admin_still_gets_roles_and_groups(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    """Regression guard: trimming the non-admin payload must not trim the admin one."""
    await create_session(test_session, test_user_id, test_session_id)
    await _seed_listing_users(test_session)

    response = test_client.get(
        '/floware/v1/users?force_fetch=1',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == 200
    users = response.json()['data']['users']
    assert len(users) >= 2
    for user in users:
        assert set(user.keys()) == {
            'id',
            'first_name',
            'last_name',
            'email',
            'username',
            'roles',
            'groups',
        }


@pytest.mark.asyncio
async def test_get_all_users_admin_can_filter_by_role(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    """The 403 above is scoped to non-admins — admins keep the filter."""
    await create_session(test_session, test_user_id, test_session_id)

    response = test_client.get(
        '/floware/v1/users?roles=admin&force_fetch=1',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_delete_user_success(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    # Create test user
    async with test_session() as session:
        user = User(
            email='delete@example.com',
            password='hashedpassword',
            first_name='Delete',
            last_name='User',
        )
        session.add(user)
        await session.flush()
        user_id = str(user.id)  # Get the ID before committing
        await session.commit()

    response = test_client.delete(
        f'/floware/v1/users?id={user_id}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    assert 'User deleted successfully' in response.json()['data']['message']
    # checking if the user is deleted from the database
    async with test_session() as session:
        user = await session.execute(select(User).where(User.id == user_id))
        user_obj = user.scalar_one()
        assert user_obj.deleted is True

        roles_res = await session.execute(
            select(UserRole).where(UserRole.user_id == user_id)
        )
        assert len(roles_res.scalars().all()) == 0


@pytest.mark.asyncio
async def test_create_user_reactivates_soft_deleted_user(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    """Test that creating a user with email of soft-deleted user reactivates the account"""
    await create_session(test_session, test_user_id, test_session_id)
    await setup_role_with_console_resource(test_session, 'test_role_id')

    # Create a soft-deleted user
    soft_deleted_user_id = str(uuid.uuid4())
    async with test_session() as session:
        # Create the user first
        user = User(
            id=soft_deleted_user_id,
            email='softdeleted@example.com',
            password='old_hashed_password',
            first_name='Old',
            last_name='Name',
            deleted=True,  # Soft deleted
        )
        session.add(user)
        await session.flush()

        # Add old role (will be replaced)
        old_role = Role(id='old_role_id', name='Old Role')
        session.add(old_role)
        await session.flush()

        # Create old role-resource mapping
        old_console_resource = Resource(
            key='old_console_access',
            value='true',
            description='Old console access',
            scope=ResourceScope.CONSOLE,
        )
        session.add(old_console_resource)
        await session.flush()

        old_role_resource = RoleResource(
            role_id='old_role_id', resource_id=old_console_resource.id
        )
        session.add(old_role_resource)

        # No user roles initially (soft delete removes them)
        await session.commit()

    # Try to create a "new" user with the same email
    new_user_data = {
        'email': 'softdeleted@example.com',  # Same email as soft-deleted user
        'password': 'NewPassword@123',
        'confirm_password': 'NewPassword@123',
        'first_name': 'New',
        'last_name': 'Name',
        'role_id': ['test_role_id'],  # New role
    }

    response = test_client.post(
        '/floware/v1/users',
        json=new_user_data,
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    # Should succeed with reactivation
    assert response.status_code == 200
    response_data = response.json()
    assert 'User account reactivated successfully' in response_data['data']['message']
    assert response_data['data']['user_id'] == soft_deleted_user_id

    # Verify user is reactivated in database
    async with test_session() as session:
        # Check user is no longer deleted
        user_result = await session.execute(
            select(User).where(User.id == soft_deleted_user_id)
        )
        reactivated_user = user_result.scalar_one()

        assert reactivated_user.deleted is False
        assert reactivated_user.first_name == 'New'  # Updated
        assert reactivated_user.last_name == 'Name'  # Updated
        assert reactivated_user.email == 'softdeleted@example.com'  # Same
        assert reactivated_user.failed_attempts == 0  # Reset
        assert reactivated_user.locked_until is None  # Reset

        # Check new roles are assigned
        user_roles_result = await session.execute(
            select(UserRole).where(UserRole.user_id == soft_deleted_user_id)
        )
        user_roles = user_roles_result.scalars().all()

        # Should have the new role assigned
        role_ids = [ur.role_id for ur in user_roles]
        assert 'test_role_id' in role_ids


@pytest.mark.asyncio
async def test_create_user_reactivation_validates_roles(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    """Test that user reactivation validates roles properly"""
    await create_session(test_session, test_user_id, test_session_id)

    # Create a soft-deleted user
    soft_deleted_user_id = str(uuid.uuid4())
    async with test_session() as session:
        user = User(
            id=soft_deleted_user_id,
            email='rolevalidation@example.com',
            password='old_password',
            first_name='Test',
            last_name='User',
            deleted=True,
        )
        session.add(user)
        await session.commit()

    # Try to reactivate with invalid role
    new_user_data = {
        'email': 'rolevalidation@example.com',
        'password': 'NewPassword@123',
        'confirm_password': 'NewPassword@123',
        'first_name': 'New',
        'last_name': 'User',
        'role_id': ['nonexistent_role_id'],  # Invalid role
    }

    response = test_client.post(
        '/floware/v1/users',
        json=new_user_data,
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    # Should fail with invalid role error - FIXED
    assert response.status_code == 400
    assert 'Invalid role IDs' in response.json()['meta']['error']

    # Verify user is still soft-deleted
    async with test_session() as session:
        user_result = await session.execute(
            select(User).where(User.id == soft_deleted_user_id)
        )
        user = user_result.scalar_one()
        assert user.deleted is True  # Still deleted


@pytest.mark.asyncio
async def test_create_user_reactivation_requires_console_resource(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    """Test that user reactivation requires console resource"""
    await create_session(test_session, test_user_id, test_session_id)

    # Create a role without console resource
    async with test_session() as session:
        role_without_console = Role(id='no_console_role', name='No Console Role')
        session.add(role_without_console)

        # Create non-console resource
        data_resource = Resource(
            key='data_access',
            value='true',
            description='Data access only',
            scope=ResourceScope.DATA,
        )
        session.add(data_resource)
        await session.flush()

        role_resource = RoleResource(
            role_id='no_console_role', resource_id=data_resource.id
        )
        session.add(role_resource)

        # Create soft-deleted user
        soft_deleted_user_id = str(uuid.uuid4())
        user = User(
            id=soft_deleted_user_id,
            email='noconsole@example.com',
            password='old_password',
            first_name='Test',
            last_name='User',
            deleted=True,
        )
        session.add(user)
        await session.commit()

    # Try to reactivate with role that has no console resource
    new_user_data = {
        'email': 'noconsole@example.com',
        'password': 'NewPassword@123',
        'confirm_password': 'NewPassword@123',
        'first_name': 'New',
        'last_name': 'User',
        'role_id': ['no_console_role'],
    }

    response = test_client.post(
        '/floware/v1/users',
        json=new_user_data,
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    # Should fail with console resource requirement
    assert response.status_code == 400
    assert 'console resource is mandatory' in response.json()['meta']['error']


@pytest.mark.asyncio
async def test_create_user_active_user_blocks_creation(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    """Test that active user with same email blocks new user creation"""
    await create_session(test_session, test_user_id, test_session_id)
    await setup_role_with_console_resource(test_session, 'test_role_id')

    # Create an active user
    async with test_session() as session:
        active_user = User(
            email='active@example.com',
            password='password',
            first_name='Active',
            last_name='User',
            deleted=False,  # Active user
        )
        session.add(active_user)
        await session.commit()

    # Try to create user with same email
    new_user_data = {
        'email': 'active@example.com',
        'password': 'NewPassword@123',
        'confirm_password': 'NewPassword@123',
        'first_name': 'New',
        'last_name': 'User',
        'role_id': ['test_role_id'],
    }

    response = test_client.post(
        '/floware/v1/users',
        json=new_user_data,
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    # Should fail with user already exists
    assert response.status_code == 400
    assert 'User with the same email already exists' in response.json()['meta']['error']


@pytest.mark.asyncio
async def test_authenticate_deleted_user(
    test_client, test_session: AsyncSession, test_user_id
):
    # Setup user + role + console resource
    from user_management_module.utils.password_utils import hash_password

    hashed_password = hash_password('test_password')

    async with test_session() as session:
        user = User(
            id=test_user_id,
            email='deleted@example.com',
            password=hashed_password,
            first_name='Del',
            last_name='User',
            deleted=True,
        )
        session.add(user)
        await session.flush()

        role = Role(id=str(uuid.uuid4()), name='Role')
        session.add(role)
        await session.flush()

        resource = Resource(
            id=str(uuid.uuid4()),
            key='console_resource',
            value='x',
            description='desc',
            scope=ResourceScope.CONSOLE,
        )
        session.add(resource)
        await session.flush()

        rr = RoleResource(role_id=role.id, resource_id=resource.id)
        session.add(rr)
        await session.flush()

        ur = UserRole(user_id=test_user_id, role_id=role.id)
        session.add(ur)
        await session.commit()

    resp = test_client.post(
        '/floware/v1/authenticate',
        json={'email': 'deleted@example.com', 'password': 'test_password'},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_user_invalidates_all_sessions_db_and_cache(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    setup_containers,
):
    # Create a separate user to delete
    async with test_session() as session:
        # inside async with test_session() as session:
        user = User(
            email='invalidate@example.com',
            password='hashed',
            first_name='Inv',
            last_name='User',
        )
        session.add(user)
        await session.flush()
        target_user_uuid = user.id  # capture before any commit
        target_user_id = str(target_user_uuid)

        # sessions — capture ids upfront
        s1_id = str(uuid.uuid4())
        s2_id = str(uuid.uuid4())
        s1 = Session(id=s1_id, user_id=target_user_uuid, device_info='dev1')
        s2 = Session(id=s2_id, user_id=target_user_uuid, device_info='dev2')
        session.add_all([s1, s2])

        # role and mapping BEFORE commit (and use captured user id, not user.id)
        role = Role(id='invalidate_role', name='Invalidate Role')
        session.add(role)
        await session.flush()
        session.add(UserRole(user_id=target_user_uuid, role_id=role.id))

        await session.commit()

    # Delete the user (soft delete)
    resp_del = test_client.delete(
        f'/floware/v1/users?id={target_user_id}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert resp_del.status_code == 200

    # Sessions should be removed from DB
    from sqlalchemy import select

    async with test_session() as session:
        result = await session.execute(
            select(Session).where(Session.user_id == target_user_uuid)
        )
        assert result.scalars().all() == []

    # Session cache keys should be removed
    _, _, user_container = setup_containers
    cache_manager = user_container.cache_manager()
    cache_manager.remove.assert_any_call(get_session_cache_key(s1_id))
    cache_manager.remove.assert_any_call(get_session_cache_key(s1_id))

    cache_manager.remove.assert_any_call(target_user_id)


@pytest.mark.asyncio
async def test_authenticate_replaces_existing_sessions(
    test_client, test_session: AsyncSession, test_user_id, setup_containers
):
    from user_management_module.utils.password_utils import hash_password
    from uuid import uuid4

    # Prepare user with role + console resource
    # 1) user
    hashed = hash_password('pw')
    async with test_session() as session:
        user = User(
            id=test_user_id,
            email='x@example.com',
            password=hashed,
            first_name='X',
            last_name='Y',
        )
        session.add(user)
        await session.flush()
        # 2) role + console resource + mapping
        role = Role(id=str(uuid4()), name='Role')
        res = Resource(
            id=str(uuid4()), key='console', value='true', scope=ResourceScope.CONSOLE
        )
        session.add_all([role, res])
        await session.flush()
        session.add(RoleResource(role_id=role.id, resource_id=res.id))
        session.add(UserRole(user_id=user.id, role_id=role.id))
        # 3) pre-existing sessions
        s1_id, s2_id = str(uuid4()), str(uuid4())
        session.add_all(
            [
                Session(id=s1_id, user_id=user.id, device_info='dev1'),
                Session(id=s2_id, user_id=user.id, device_info='dev2'),
            ]
        )
        await session.commit()

    # Login: should remove s1/s2 and create a fresh session
    resp = test_client.post(
        '/floware/v1/authenticate', json={'email': 'x@example.com', 'password': 'pw'}
    )
    assert resp.status_code == 200

    # DB sessions for user should be 1 (the newly created one)
    async with test_session() as session:
        rows = (
            (
                await session.execute(
                    select(Session).where(Session.user_id == test_user_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1

    # Cache invalidations were called for old sessions
    _, _, user_container = setup_containers
    cache_manager = user_container.cache_manager()
    cache_manager.remove.assert_any_call(get_session_cache_key(s1_id))
    cache_manager.remove.assert_any_call(get_session_cache_key(s1_id))


@pytest.mark.asyncio
async def test_authenticate_enabled_user_without_roles_fails(
    test_client, test_session: AsyncSession, test_user_id
):
    from user_management_module.utils.password_utils import hash_password

    hashed_password = hash_password('test_password')

    async with test_session() as session:
        # user enabled
        user = User(
            id=test_user_id,
            email='norole@example.com',
            password=hashed_password,
            first_name='No',
            last_name='Role',
            deleted=False,
        )
        session.add(user)
        await session.flush()

        # create role + console resource and mapping, then remove the mapping to simulate deleted roles
        role = Role(id=str(uuid.uuid4()), name='Role')
        session.add(role)
        await session.flush()

        resource = Resource(
            id=str(uuid.uuid4()),
            key='console_resource',
            value='x',
            description='desc',
            scope=ResourceScope.CONSOLE,
        )
        session.add(resource)
        await session.flush()

        rr = RoleResource(role_id=role.id, resource_id=resource.id)
        session.add(rr)
        await session.flush()

        ur = UserRole(user_id=test_user_id, role_id=role.id)
        session.add(ur)
        await session.flush()

        # Remove user roles
        await session.delete(ur)
        await session.commit()

    resp = test_client.post(
        '/floware/v1/authenticate',
        json={'email': 'norole@example.com', 'password': 'test_password'},
    )
    # Should fail because there is no console role now
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_send_reset_password_email(
    test_client,
    setup_containers,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    _, _, user_container = setup_containers
    email_service = user_container.email_send_service()
    email_service.send.reset_mock()

    # Create test user and session
    await create_session(test_session, test_user_id, test_session_id)

    # Create another test user for password reset
    async with test_session() as session:
        user = User(
            email='reset@example.com',
            password='hashedpassword',
            first_name='Reset',
            last_name='User',
        )
        session.add(user)
        await session.commit()

    response = test_client.post(
        '/floware/v1/user/send-reset-password-email?email=reset@example.com',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    # Same message the unknown-email, deleted and locked cases return; the mail
    # itself is what separates a live account from those, not the reply.
    assert 'If an account exists' in response.json()['data']['message']
    email_service.send.assert_called_once()


@pytest.mark.asyncio
async def test_reset_password(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    # Create test user
    await create_session(test_session, test_user_id, test_session_id)

    async with test_session() as session:
        user = User(
            email='reset@example.com',
            password='oldpassword',
            first_name='Reset',
            last_name='User',
        )
        session.add(user)
        await session.commit()

    reset_data = {
        'secret_token': 'mock_token',  # Use the mock token that matches our mock setup
        'new_password': 'Test@123',  # Updated password with special character
        'confirm_password': 'Test@123',
    }

    response = test_client.post(
        '/floware/v1/user/reset-password',
        json=reset_data,
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    assert (
        'password has been updated successfully' in response.json()['data']['message']
    )


@pytest.mark.asyncio
async def test_reset_password_mismatched_confirmation(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)

    reset_data = {
        'secret_token': 'mock_token',
        'new_password': 'Test@123',
        'confirm_password': 'Different@123',
    }

    response = test_client.post(
        '/floware/v1/user/reset-password',
        json=reset_data,
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 422
    assert 'do not match' in str(response.json()).lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'password',
    [
        'test@123',  # no uppercase
        'TEST@123',  # no lowercase
        'Test1234',  # no special
        'Te@1',  # too short
    ],
)
async def test_create_user_rejects_weak_password(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    password,
):
    await create_session(test_session, test_user_id, test_session_id)
    await setup_role_with_console_resource(test_session, 'test_role_id')

    response = test_client.post(
        '/floware/v1/users',
        json={
            'email': 'weak@example.com',
            'password': password,
            'confirm_password': password,
            'first_name': 'Test',
            'last_name': 'User',
            'role_id': ['test_role_id'],
        },
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_user_rejects_missing_confirm_password(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    await setup_role_with_console_resource(test_session, 'test_role_id')

    response = test_client.post(
        '/floware/v1/users',
        json={
            'email': 'noconfirm@example.com',
            'password': 'Test@123',
            'first_name': 'Test',
            'last_name': 'User',
            'role_id': ['test_role_id'],
        },
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_user_rejects_invalid_email_and_name(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    await setup_role_with_console_resource(test_session, 'test_role_id')

    response = test_client.post(
        '/floware/v1/users',
        json={
            'email': 'not-an-email',
            'password': 'Test@123',
            'confirm_password': 'Test@123',
            'first_name': 'Test123',
            'last_name': 'User!',
            'role_id': ['test_role_id'],
        },
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_user_rejects_non_uuid_group_ids(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    await setup_role_with_console_resource(test_session, 'test_role_id')

    response = test_client.post(
        '/floware/v1/users',
        json={
            'email': 'badgroup@example.com',
            'password': 'Test@123',
            'confirm_password': 'Test@123',
            'first_name': 'Test',
            'last_name': 'User',
            'role_id': ['test_role_id'],
            'group_ids': ['not-a-uuid'],
        },
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_user_rejects_password_without_confirm(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    async with test_session() as session:
        user = User(
            email='update_no_confirm@example.com',
            password='hashedpassword',
            first_name='Test',
            last_name='User',
        )
        session.add(user)
        await session.flush()
        user_id = str(user.id)
        await session.commit()

    response = test_client.patch(
        '/floware/v1/users',
        json={'user_id': user_id, 'password': 'Test@123'},
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_user_rejects_invalid_user_id(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)

    response = test_client.patch(
        '/floware/v1/users',
        json={'user_id': 'not-a-uuid', 'first_name': 'Test'},
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'password',
    ['test@123', 'TEST@123', 'Test1234', 'Te@1'],
)
async def test_reset_password_rejects_weak_password(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    password,
):
    await create_session(test_session, test_user_id, test_session_id)

    response = test_client.post(
        '/floware/v1/user/reset-password',
        json={
            'secret_token': 'mock_token',
            'new_password': password,
            'confirm_password': password,
        },
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_send_reset_password_email_rejects_invalid_email(
    test_client,
    setup_containers,
    mock_auth_admin_user_functions,
):
    response = test_client.post(
        '/floware/v1/user/send-reset-password-email?email=not-an-email',
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_user_rejects_invalid_uuid(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)

    response = test_client.delete(
        '/floware/v1/users?id=not-a-uuid',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 400
    assert 'invalid user id' in response.json()['meta']['error'].lower()


@pytest.mark.asyncio
async def test_unblock_user_rejects_invalid_uuid(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)

    response = test_client.patch(
        '/floware/v1/users/not-a-uuid/unblock',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 400
    assert 'invalid user id' in response.json()['meta']['error'].lower()


@pytest.mark.asyncio
async def test_get_all_users_rejects_invalid_pagination(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)

    response = test_client.get(
        '/floware/v1/users?limit=0&offset=-1',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_whoami_endpoint(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    response = test_client.get(
        '/floware/v1/whoami', headers={'Authorization': f'Bearer {auth_token}'}
    )
    assert response.status_code == 200
    assert 'user' in response.json()['data']


@pytest.mark.asyncio
async def test_update_user_invalid_role(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    update_data = {
        'user_id': test_user_id,  # Use the actual UUID from the fixture
        'add_role_ids': ['invalid_role_id'],
    }

    response = test_client.patch(
        '/floware/v1/users',
        json=update_data,
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == 400
    assert 'Invalid role IDs' in response.json()['meta']['error']


# adding test for non-admin user
@pytest.mark.asyncio
async def test_non_admin_user_create_user(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    new_user_data = {
        'email': 'test2@example.com',
        'password': 'Test@123',  # Updated password with special character
        'confirm_password': 'Test@123',
        'first_name': 'Test',
        'last_name': 'User',
        'role_id': ['test_role_id'],
    }
    response = test_client.post(
        '/floware/v1/users',
        json=new_user_data,
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 401


# chekcing when admin user is created and all roles are assigned to the user
@pytest.mark.asyncio
async def test_admin_user_create_user(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mocking_user_controller_is_admin,
):
    await create_session(test_session, test_user_id, test_session_id)
    new_user_data = {
        'email': 'test2@example.com',
        'password': 'Test@123',  # Updated password with special character
        'confirm_password': 'Test@123',
        'first_name': 'Test',
        'last_name': 'User',
        'role_id': ['test_role_id', 'test_role_id2'],
    }

    async with test_session() as session:
        # Create roles
        role1 = Role(id='test_role_id', name='Test Role')
        role2 = Role(id='test_role_id2', name='Test Role 2')
        session.add_all([role1, role2])
        await session.flush()

        # Create console resources
        console_resource1 = Resource(
            id=str(uuid.uuid4()),
            key='console_access',
            value='true',
            description='Console access resource',
            scope=ResourceScope.CONSOLE,
        )
        console_resource2 = Resource(
            id=str(uuid.uuid4()),
            key='console_manage',
            value='true',
            description='Console management resource',
            scope=ResourceScope.CONSOLE,
        )
        session.add_all([console_resource1, console_resource2])
        await session.flush()

        # Link roles with console resources
        role_resource1 = RoleResource(
            role_id='test_role_id', resource_id=console_resource1.id
        )
        role_resource2 = RoleResource(
            role_id='test_role_id2', resource_id=console_resource2.id
        )
        session.add_all([role_resource1, role_resource2])
        await session.commit()

    response = test_client.post(
        '/floware/v1/users',
        json=new_user_data,
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    # checking if the role is assigned to the user in user_role table
    new_user_id = response.json()['data']['user_id']
    async with test_session() as session:
        user_role = await session.execute(
            select(UserRole).where(UserRole.user_id == new_user_id)
        )
        user_role = user_role.scalars().all()
        assert len(user_role) == 2


# chekcing when admin user is created and all roles are assigned to the user
@pytest.mark.asyncio
async def test_admin_user_creat_non_admin_user(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mocking_user_controller_is_admin,
    mocking_user_controller_get_current_user,
):
    await create_session(test_session, test_user_id, test_session_id)
    new_user_data = {
        'email': 'test2@example.com',
        'password': 'Test@123',  # Updated password with special character
        'confirm_password': 'Test@123',
        'first_name': 'Test',
        'last_name': 'User',
        'role_id': ['test_role_id'],
    }

    async with test_session() as session:
        # Create roles
        role1 = Role(id='test_role_id', name='Test Role')
        role2 = Role(id='test_role_id2', name='Test Role 2')
        session.add_all([role1, role2])
        await session.flush()

        # Create console resources
        console_resource1 = Resource(
            id=str(uuid.uuid4()),
            key='console_access',
            value='true',
            description='Console access resource',
            scope=ResourceScope.CONSOLE,
        )
        console_resource2 = Resource(
            id=str(uuid.uuid4()),
            key='console_manage',
            value='true',
            description='Console management resource',
            scope=ResourceScope.CONSOLE,
        )
        session.add_all([console_resource1, console_resource2])
        await session.flush()

        # Link roles with console resources
        role_resource1 = RoleResource(
            role_id='test_role_id', resource_id=console_resource1.id
        )
        role_resource2 = RoleResource(
            role_id='test_role_id2', resource_id=console_resource2.id
        )
        session.add_all([role_resource1, role_resource2])
        await session.commit()

    response = test_client.post(
        '/floware/v1/users',
        json=new_user_data,
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    # checking if the role is assigned to the user in user_role table
    new_user_id = response.json()['data']['user_id']
    async with test_session() as session:
        user_role = await session.execute(
            select(UserRole).where(UserRole.user_id == new_user_id)
        )
        user_role = user_role.scalars().all()
        assert len(user_role) == 1


@pytest.mark.asyncio
async def test_admin_user_creat_non_admin_user_with_invalid_role(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mocking_user_controller_is_admin,
    mocking_user_controller_get_current_user,
):
    await create_session(test_session, test_user_id, test_session_id)
    new_user_data = {
        'email': 'test2@example.com',
        'password': 'Test@123',  # Updated password with special character
        'confirm_password': 'Test@123',
        'first_name': 'Test',
        'last_name': 'User',
        'role_id': ['123213123'],
    }

    async with test_session() as session:
        # Create roles
        role1 = Role(id='test_role_id', name='Test Role')
        role2 = Role(id='test_role_id2', name='Test Role 2')
        session.add_all([role1, role2])
        await session.flush()

        # Create console resources
        console_resource1 = Resource(
            id=str(uuid.uuid4()),
            key='console_access',
            value='true',
            description='Console access resource',
            scope=ResourceScope.CONSOLE,
        )
        console_resource2 = Resource(
            id=str(uuid.uuid4()),
            key='console_manage',
            value='true',
            description='Console management resource',
            scope=ResourceScope.CONSOLE,
        )
        session.add_all([console_resource1, console_resource2])
        await session.flush()

        # Link roles with console resources
        role_resource1 = RoleResource(
            role_id='test_role_id', resource_id=console_resource1.id
        )
        role_resource2 = RoleResource(
            role_id='test_role_id2', resource_id=console_resource2.id
        )
        session.add_all([role_resource1, role_resource2])
        await session.commit()

    response = test_client.post(
        '/floware/v1/users',
        json=new_user_data,
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_admin_user_creat_non_admin_user_with_empty_role(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mocking_user_controller_is_admin,
    mocking_user_controller_get_current_user,
):
    """An empty role list is still rejected, but by the console-resource guard.

    Roles became optional on the schema when groups landed, since a user may
    draw their access from a group instead. Supplying neither roles nor a group
    that grants console access is now a 400 from that check rather than a 422
    from the request model.
    """
    await create_session(test_session, test_user_id, test_session_id)
    new_user_data = {
        'email': 'test2@example.com',
        'password': 'Test@123',  # Updated password with special character
        'confirm_password': 'Test@123',
        'first_name': 'Test',
        'last_name': 'User',
        'role_id': [],
    }

    response = test_client.post(
        '/floware/v1/users',
        json=new_user_data,
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 400
    assert 'console resource' in str(response.json())


@pytest.mark.asyncio
async def test_unblock_user_success(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    """Test successful user unblock by admin"""
    await create_session(test_session, test_user_id, test_session_id)

    current_time = datetime.now(timezone.utc)
    locked_until = current_time + timedelta(hours=1)  # User is locked

    # Create a locked user
    locked_user_id = None
    async with test_session() as session:
        locked_user = User(
            email='locked_user@example.com',
            password='hashedpassword',
            first_name='Locked',
            last_name='User',
            failed_attempts=3,
            locked_until=locked_until,
            last_failed_attempt=current_time,
        )
        session.add(locked_user)
        await session.flush()
        locked_user_id = str(locked_user.id)
        await session.commit()

    # Admin unblocks the user
    response = test_client.patch(
        f'/floware/v1/users/{locked_user_id}/unblock',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == 200
    assert 'successfully unblocked' in response.json()['data']['message']
    assert locked_user_id in response.json()['data']['message']

    # Verify user is actually unblocked in database
    async with test_session() as session:
        unblocked_user = await session.execute(
            select(User).where(User.email == 'locked_user@example.com')
        )
        unblocked_user = unblocked_user.scalars().first()
        assert unblocked_user.failed_attempts == 0
        assert unblocked_user.locked_until is None
        assert unblocked_user.last_failed_attempt is None


@pytest.mark.asyncio
async def test_unblock_nonexistent_user(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    """Test unblock attempt for non-existent user"""
    await create_session(test_session, test_user_id, test_session_id)

    # Use a fake UUID for non-existent user
    fake_user_id = str(uuid.uuid4())

    response = test_client.patch(
        f'/floware/v1/users/{fake_user_id}/unblock',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == 404
    assert 'not found' in response.json()['meta']['error']
    assert fake_user_id in response.json()['meta']['error']


@pytest.mark.asyncio
async def test_unblock_user_non_admin_access_denied(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    """Test unblock access denied for non-admin user"""
    await create_session(test_session, test_user_id, test_session_id)

    # Create a locked user
    current_time = datetime.now(timezone.utc)
    locked_until = current_time + timedelta(hours=1)

    locked_user_id = None
    async with test_session() as session:
        locked_user = User(
            email='locked_user@example.com',
            password='hashedpassword',
            first_name='Locked',
            last_name='User',
            failed_attempts=3,
            locked_until=locked_until,
            last_failed_attempt=current_time,
        )
        session.add(locked_user)
        await session.flush()
        locked_user_id = str(locked_user.id)
        await session.commit()

    # Non-admin user attempts to unblock
    response = test_client.patch(
        f'/floware/v1/users/{locked_user_id}/unblock',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    assert response.status_code == 401
    assert 'Access denied' in response.json()['meta']['error']

    # Verify user is still locked in database
    async with test_session() as session:
        still_locked_user = await session.execute(
            select(User).where(User.email == 'locked_user@example.com')
        )
        still_locked_user = still_locked_user.scalars().first()
        assert still_locked_user.failed_attempts == 3
        assert still_locked_user.locked_until is not None


@pytest.mark.asyncio
async def test_unblock_already_unlocked_user(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    """Test unblock operation on a user that is already unlocked"""
    await create_session(test_session, test_user_id, test_session_id)

    # Create an unlocked user (no lockout fields set)
    unlocked_user_id = None
    async with test_session() as session:
        unlocked_user = User(
            email='unlocked_user@example.com',
            password='hashedpassword',
            first_name='Unlocked',
            last_name='User',
            failed_attempts=0,  # No failed attempts
            locked_until=None,  # Not locked
            last_failed_attempt=None,  # No previous failed attempts
        )
        session.add(unlocked_user)
        await session.flush()
        unlocked_user_id = str(unlocked_user.id)
        await session.commit()

    # Admin attempts to unblock already unlocked user
    response = test_client.patch(
        f'/floware/v1/users/{unlocked_user_id}/unblock',
        headers={'Authorization': f'Bearer {auth_token}'},
    )

    # Should still return success (idempotent operation)
    assert response.status_code == 200
    assert 'successfully unblocked' in response.json()['data']['message']


@pytest.mark.asyncio
async def test_get_user_by_id_includes_lockout_fields(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    setup_containers,
):
    """GET /users/{id} returns lockout/login fields from user.to_dict()."""
    await create_session(test_session, test_user_id, test_session_id)

    # Bypass the hour-long user cache so this assertion hits the database.
    _, _, user_container = setup_containers
    user_container.cache_manager().get_str.return_value = None

    locked_until = datetime.now(timezone.utc) + timedelta(hours=2)
    last_failed = datetime.now(timezone.utc) - timedelta(minutes=1)
    last_login = datetime.now(timezone.utc) - timedelta(days=1)
    target_user_id = None

    async with test_session() as session:
        target = User(
            email='lockout_fields@example.com',
            password='hashedpassword',
            first_name='Lockout',
            last_name='Fields',
            failed_attempts=3,
            locked_until=locked_until,
            last_failed_attempt=last_failed,
            last_login_at=last_login,
        )
        session.add(target)
        await session.flush()
        target_user_id = str(target.id)
        await session.commit()

    response = test_client.get(
        f'/floware/v1/users/{target_user_id}?force_fetch=1',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    user_data = response.json()['data']['user']
    assert user_data['failed_attempts'] == 3
    assert user_data['locked_until'] is not None
    assert user_data['last_failed_attempt'] is not None
    assert user_data['last_login_at'] is not None
    assert user_data['email'] == 'lockout_fields@example.com'


@pytest.mark.asyncio
async def test_delete_user_blocks_last_admin_self_delete(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    async with test_session() as session:
        role = Role(id='test_role_id', name='admin')
        session.add(role)
        await session.flush()
        session.add(UserRole(user_id=test_user_id, role_id='test_role_id'))
        await session.commit()

    response = test_client.delete(
        f'/floware/v1/users?id={test_user_id}',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 400
    assert 'admin is mandatory' in response.json()['meta']['error'].lower()


@pytest.mark.asyncio
async def test_reset_password_expired_token(
    test_client,
    core_containers,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    import jwt

    await create_session(test_session, test_user_id, test_session_id)
    original = core_containers.token_service.decode_token
    core_containers.token_service.decode_token.side_effect = jwt.ExpiredSignatureError(
        'expired'
    )
    try:
        response = test_client.post(
            '/floware/v1/user/reset-password',
            json={
                'secret_token': 'expired_token',
                'new_password': 'Test@123',
                'confirm_password': 'Test@123',
            },
            headers={'Authorization': f'Bearer {auth_token}'},
        )
        assert response.status_code == 401
        assert 'expired' in response.json()['meta']['error'].lower()
    finally:
        core_containers.token_service.decode_token.side_effect = None
        core_containers.token_service.decode_token.return_value = original.return_value


@pytest.mark.asyncio
async def test_reset_password_missing_cache_code(
    test_client,
    core_containers,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    original_get = core_containers.cache_manager.get_str.side_effect
    original_decode = core_containers.token_service.decode_token.return_value
    core_containers.token_service.decode_token.return_value = {'code': 'missing_code'}
    core_containers.cache_manager.get_str.side_effect = lambda key: None
    try:
        response = test_client.post(
            '/floware/v1/user/reset-password',
            json={
                'secret_token': 'token',
                'new_password': 'Test@123',
                'confirm_password': 'Test@123',
            },
            headers={'Authorization': f'Bearer {auth_token}'},
        )
        assert response.status_code == 404
        err = response.json()['meta']['error'].lower()
        assert 'expired' in err or 'verify' in err
    finally:
        core_containers.cache_manager.get_str.side_effect = original_get
        core_containers.token_service.decode_token.return_value = original_decode


@pytest.mark.asyncio
async def test_get_user_by_id_invalid_uuid(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    response = test_client.get(
        '/floware/v1/users/not-a-uuid?force_fetch=1',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_user_by_id_deleted_returns_404(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    async with test_session() as session:
        user = User(
            email='deleted_get@example.com',
            password='hashed',
            first_name='Del',
            last_name='User',
            deleted=True,
        )
        session.add(user)
        await session.flush()
        deleted_id = str(user.id)
        await session.commit()

    response = test_client.get(
        f'/floware/v1/users/{deleted_id}?force_fetch=1',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_user_by_id_non_admin_denied_without_flag(
    test_client,
    mock_auth_non_admin_user_functions,
    set_non_admin_data_access_flag,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    set_non_admin_data_access_flag(False)
    await create_session(test_session, test_user_id, test_session_id)
    response = test_client.get(
        f'/floware/v1/users/{test_user_id}?force_fetch=1',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_user_by_id_non_admin_allowed_with_flag(
    test_client,
    mock_auth_non_admin_user_functions,
    patch_feature_flag,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    # get_user goes through can_read_users in user_utils, so patch both namespaces.
    patch_feature_flag('user_management_module.controllers.user_controller', True)
    patch_feature_flag('user_management_module.utils.user_utils', True)
    await create_session(test_session, test_user_id, test_session_id)
    response = test_client.get(
        f'/floware/v1/users/{test_user_id}?force_fetch=1',
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 200
    assert response.json()['data']['user']['id'] == test_user_id


@pytest.mark.asyncio
async def test_whoami_admin_payload_shape(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    response = test_client.get(
        '/floware/v1/whoami', headers={'Authorization': f'Bearer {auth_token}'}
    )
    assert response.status_code == 200
    data = response.json()['data']
    assert 'user' in data
    assert 'resource' in data
    assert set(data['resource'].keys()) >= {
        'console_resources',
        'dashboards',
        'routes',
        'data',
    }
    # Admin path leaves routes/data empty lists.
    assert data['resource']['routes'] == []
    assert data['resource']['data'] == []


@pytest.mark.asyncio
async def test_create_user_duplicate_username(
    test_client,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
):
    await create_session(test_session, test_user_id, test_session_id)
    await setup_role_with_console_resource(test_session, 'test_role_id')
    async with test_session() as session:
        session.add(
            User(
                email='taken@example.com',
                username='taken_user',
                password='hashed',
                first_name='Taken',
                last_name='User',
            )
        )
        await session.commit()

    response = test_client.post(
        '/floware/v1/users',
        json={
            'email': 'new@example.com',
            'username': 'taken_user',
            'password': 'Test@123',
            'confirm_password': 'Test@123',
            'first_name': 'New',
            'last_name': 'User',
            'role_id': ['test_role_id'],
        },
        headers={'Authorization': f'Bearer {auth_token}'},
    )
    assert response.status_code == 400
    assert 'username' in response.json()['meta']['error'].lower()


@pytest.mark.asyncio
async def test_send_reset_password_email_generic_when_mail_fails(
    test_client,
    setup_containers,
    core_containers,
    mock_auth_admin_user_functions,
    test_session,
    test_user_id,
    test_session_id,
):
    await create_session(test_session, test_user_id, test_session_id)
    async with test_session() as session:
        session.add(
            User(
                email='mailfail@example.com',
                password='hashedpassword',
                first_name='Mail',
                last_name='Fail',
            )
        )
        await session.commit()

    original = core_containers.email_send_service.send
    core_containers.email_send_service.send.side_effect = ValueError('smtp down')
    try:
        response = test_client.post(
            '/floware/v1/user/send-reset-password-email?email=mailfail@example.com',
        )
        assert response.status_code == 200
        assert 'if an account exists' in response.json()['data']['message'].lower()
    finally:
        core_containers.email_send_service.send.side_effect = None
        core_containers.email_send_service.send = original
