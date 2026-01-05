from datetime import datetime, timedelta, timezone
import os
from unittest.mock import Mock
from uuid import uuid4

from db_repo_module.models.resource import Resource
from db_repo_module.models.resource import ResourceScope
from db_repo_module.models.role import Role
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.models.session import Session
from db_repo_module.models.user import User
from db_repo_module.models.user_role import UserRole
from dependency_injector import providers
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from user_management_module.utils.password_utils import hash_password


@pytest.mark.asyncio
async def test_authenticate(test_client, test_session: AsyncSession, test_user_id):
    # Create test IDs
    role_id = str(uuid4())
    resource_id = str(uuid4())

    # Hash the password before storing it
    hashed_password = hash_password('test_password')

    async with test_session() as session:
        # First create the user
        user = User(
            id=test_user_id,
            email='test@example.com',
            password=hashed_password,
            first_name='Test',
            last_name='User',
        )
        session.add(user)
        await session.commit()

        # Then create the role
        role = Role(id=role_id, name='Test Role', description='Test Role Description')
        session.add(role)
        await session.commit()

        # Then create the resource
        resource = Resource(
            id=resource_id,
            key='console_resource',
            value='test_resource',
            description='Test Resource Description',
            scope=ResourceScope.CONSOLE,
        )
        session.add(resource)
        await session.commit()

        # Then create role-resource mapping
        role_resource = RoleResource(role_id=role_id, resource_id=resource_id)
        session.add(role_resource)
        await session.commit()

        # Finally create user-role mapping
        user_role = UserRole(user_id=test_user_id, role_id=role_id)
        session.add(user_role)
        await session.commit()

    response = test_client.post(
        '/floware/v1/authenticate',
        json={'email': 'test@example.com', 'password': 'test_password'},
    )

    assert response.status_code == 200
    assert response.json()['data']['user']['access_token'] == 'mock_token'


@pytest.mark.asyncio
async def test_authenticate_invalid_role(
    test_client, test_session: AsyncSession, test_user_id
):
    # Hash the password before storing it
    hashed_password = hash_password('test_password')

    async with test_session() as session:
        # First create the user
        user = User(
            id=test_user_id,
            email='test@example.com',
            password=hashed_password,
            first_name='Test',
            last_name='User',
        )
        session.add(user)
        await session.commit()

    response = test_client.post(
        '/floware/v1/authenticate',
        json={'email': 'test@example.com', 'password': 'test_password'},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_authenticate_invalid_password(
    test_client, test_session: AsyncSession, test_user_id
):
    # Hash the password before storing it
    hashed_password = hash_password('test_password')

    async with test_session() as session:
        # First create the user
        user = User(
            id=test_user_id,
            email='test@example.com',
            password=hashed_password,
            first_name='Test',
            last_name='User',
        )
        session.add(user)
        await session.commit()

    response = test_client.post(
        '/floware/v1/authenticate',
        json={'email': 'test@example.com', 'password': 'invalid_password'},
    )

    assert response.status_code == 403


# testing auth logout
@pytest.mark.asyncio
async def test_logout(
    test_client, auth_token, test_session: AsyncSession, test_user_id, test_session_id
):
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
    response = test_client.post(
        '/floware/v1/logout', headers={'Authorization': f'Bearer {auth_token}'}
    )
    assert response.status_code == 200


# logout test with invalid cache
@pytest.mark.asyncio
async def test_logout_invalid_cache(
    test_client,
    auth_token,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    setup_containers,
):
    # Get the cache manager mock and set it to return None
    _, _, user_container = setup_containers
    cache_manager_mock = Mock()
    cache_manager_mock.get_str = Mock(return_value=None)
    user_container.cache_manager.override(
        providers.Singleton(lambda: cache_manager_mock)
    )

    # Create a session in the database but not in cache
    response = test_client.post(
        '/floware/v1/logout', headers={'Authorization': f'Bearer {auth_token}'}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_authenticate_multiple_failed_attempts_lockout(
    test_client, test_session: AsyncSession, test_user_id
):
    """Test that multiple failed login attempts result in account lockout"""
    # Get max failed attempts from environment variable, default to 3
    max_failed_attempts = int(os.getenv('MAX_FAILED_ATTEMPTS', 3))

    # Create test IDs
    role_id = str(uuid4())
    resource_id = str(uuid4())
    hashed_password = hash_password('correct_password')

    async with test_session() as session:
        # Create user
        user = User(
            id=test_user_id,
            email='lockout_test@example.com',
            password=hashed_password,
            first_name='Test',
            last_name='User',
        )
        session.add(user)
        await session.commit()

        # Create role and resource setup for console access
        role = Role(id=role_id, name='Test Role')
        resource = Resource(
            id=resource_id,
            key='console_resource',
            value='test_resource',
            scope=ResourceScope.CONSOLE,
        )
        session.add_all([role, resource])
        await session.commit()

        # Create role-resource and user-role mappings
        role_resource = RoleResource(role_id=role_id, resource_id=resource_id)
        user_role = UserRole(user_id=test_user_id, role_id=role_id)
        session.add_all([role_resource, user_role])
        await session.commit()

    # Perform failed login attempts up to the limit
    for attempt in range(1, max_failed_attempts):
        response = test_client.post(
            '/floware/v1/authenticate',
            json={'email': 'lockout_test@example.com', 'password': 'wrong_password'},
        )
        assert response.status_code == 403

    # Final failed login attempt should trigger lockout
    response = test_client.post(
        '/floware/v1/authenticate',
        json={'email': 'lockout_test@example.com', 'password': 'wrong_password'},
    )
    assert response.status_code == 423
    assert 'Account locked' in response.json()['meta']['error']
    assert 'Try again in' in response.json()['meta']['error']

    # Even correct password should be rejected when locked
    response = test_client.post(
        '/floware/v1/authenticate',
        json={'email': 'lockout_test@example.com', 'password': 'correct_password'},
    )
    assert response.status_code == 423
    assert 'Account locked' in response.json()['meta']['error']


@pytest.mark.asyncio
async def test_authenticate_with_already_locked_account(
    test_client, test_session: AsyncSession, test_user_id
):
    """Test authentication attempt with an already locked account"""
    # Get max failed attempts from environment variable, default to 3
    max_failed_attempts = int(os.getenv('MAX_FAILED_ATTEMPTS', 3))

    hashed_password = hash_password('test_password')
    current_time = datetime.now(timezone.utc)
    locked_until = current_time + timedelta(hours=1)  # Locked for 1 hour

    async with test_session() as session:
        # Create locked user
        user = User(
            id=test_user_id,
            email='locked_user@example.com',
            password=hashed_password,
            first_name='Locked',
            last_name='User',
            failed_attempts=max_failed_attempts,
            locked_until=locked_until,
            last_failed_attempt=current_time,
        )
        session.add(user)
        await session.commit()

    # Attempt login with correct credentials should still be rejected
    response = test_client.post(
        '/floware/v1/authenticate',
        json={'email': 'locked_user@example.com', 'password': 'test_password'},
    )

    assert response.status_code == 423
    assert 'Account locked' in response.json()['meta']['error']
    assert 'Try again in' in response.json()['meta']['error']


@pytest.mark.asyncio
async def test_authenticate_resets_failed_attempts_on_success(
    test_client, test_session: AsyncSession, test_user_id
):
    """Test that successful login resets failed attempts counter"""
    # Get max failed attempts from environment variable, default to 3
    max_failed_attempts = int(os.getenv('MAX_FAILED_ATTEMPTS', 3))

    # Create test IDs
    role_id = str(uuid4())
    resource_id = str(uuid4())
    hashed_password = hash_password('test_password')
    current_time = datetime.now(timezone.utc)

    async with test_session() as session:
        # Create user with some failed attempts but not locked
        user = User(
            id=test_user_id,
            email='reset_attempts@example.com',
            password=hashed_password,
            first_name='Test',
            last_name='User',
            failed_attempts=max_failed_attempts
            - 1,  # Has failed attempts but not locked yet
            last_failed_attempt=current_time - timedelta(minutes=30),
        )
        session.add(user)
        await session.commit()

        # Create role and resource setup for console access
        role = Role(id=role_id, name='Test Role')
        resource = Resource(
            id=resource_id,
            key='console_resource',
            value='test_resource',
            scope=ResourceScope.CONSOLE,
        )
        session.add_all([role, resource])
        await session.commit()

        # Create role-resource and user-role mappings
        role_resource = RoleResource(role_id=role_id, resource_id=resource_id)
        user_role = UserRole(user_id=test_user_id, role_id=role_id)
        session.add_all([role_resource, user_role])
        await session.commit()

    # Successful login should reset failed attempts
    response = test_client.post(
        '/floware/v1/authenticate',
        json={'email': 'reset_attempts@example.com', 'password': 'test_password'},
    )

    assert response.status_code == 200
    assert response.json()['data']['user']['access_token'] == 'mock_token'

    # Verify failed attempts were reset in database
    async with test_session() as session:
        updated_user = await session.get(User, test_user_id)
        assert updated_user.failed_attempts == 0
        assert updated_user.locked_until is None
        assert updated_user.last_failed_attempt is None


@pytest.mark.asyncio
async def test_authenticate_inactive_account_feature_disabled(
    test_client, test_session: AsyncSession, test_user_id, monkeypatch, mock_config
):
    """Test that inactive users can login when feature flag is disabled"""
    # Get threshold from config (same config that service uses)
    threshold_days = int(mock_config['auth']['inactive_days_threshold'])

    # Mock the feature flag to be disabled
    def mock_is_feature_enabled(feature: str) -> bool:
        if feature == 'INACTIVE_ACCOUNT_DISABLE_FLAG':
            return False
        return False

    monkeypatch.setattr(
        'common_module.feature.feature_flag.is_feature_enabled', mock_is_feature_enabled
    )
    monkeypatch.setattr(
        'user_management_module.controllers.auth_controller.is_feature_enabled',
        mock_is_feature_enabled,
    )

    # Create test IDs
    role_id = str(uuid4())
    resource_id = str(uuid4())
    hashed_password = hash_password('test_password')

    # Create user inactive for (threshold + 30) days
    inactive_date = datetime.now(timezone.utc) - timedelta(days=threshold_days + 30)

    async with test_session() as session:
        # Create user with old last_login_at
        user = User(
            id=test_user_id,
            email='inactive_test@example.com',
            password=hashed_password,
            first_name='Inactive',
            last_name='User',
            last_login_at=inactive_date,
        )
        session.add(user)
        await session.commit()

        # Create role and resource setup for console access
        role = Role(id=role_id, name='Test Role')
        resource = Resource(
            id=resource_id,
            key='console_resource',
            value='test_resource',
            scope=ResourceScope.CONSOLE,
        )
        session.add_all([role, resource])
        await session.commit()

        # Create role-resource and user-role mappings
        role_resource = RoleResource(role_id=role_id, resource_id=resource_id)
        user_role = UserRole(user_id=test_user_id, role_id=role_id)
        session.add_all([role_resource, user_role])
        await session.commit()

    # Should succeed even though user is inactive (feature disabled)
    response = test_client.post(
        '/floware/v1/authenticate',
        json={'email': 'inactive_test@example.com', 'password': 'test_password'},
    )

    assert response.status_code == 200
    assert response.json()['data']['user']['access_token'] == 'mock_token'


@pytest.mark.asyncio
async def test_authenticate_inactive_account_feature_enabled_first_time_user(
    test_client, test_session: AsyncSession, test_user_id, monkeypatch, mock_config
):
    """Test that first-time users (no last_login_at) can login when feature is enabled"""

    # Mock the feature flag to be enabled
    def mock_is_feature_enabled(feature: str) -> bool:
        if feature == 'INACTIVE_ACCOUNT_DISABLE_FLAG':
            return True
        return False

    monkeypatch.setattr(
        'common_module.feature.feature_flag.is_feature_enabled', mock_is_feature_enabled
    )
    monkeypatch.setattr(
        'user_management_module.controllers.auth_controller.is_feature_enabled',
        mock_is_feature_enabled,
    )

    # Create test IDs
    role_id = str(uuid4())
    resource_id = str(uuid4())
    hashed_password = hash_password('test_password')

    async with test_session() as session:
        # Create user with no last_login_at (first-time user)
        user = User(
            id=test_user_id,
            email='firsttime_test@example.com',
            password=hashed_password,
            first_name='FirstTime',
            last_name='User',
            # last_login_at is None by default
        )
        session.add(user)
        await session.commit()

        # Create role and resource setup for console access
        role = Role(id=role_id, name='Test Role')
        resource = Resource(
            id=resource_id,
            key='console_resource',
            value='test_resource',
            scope=ResourceScope.CONSOLE,
        )
        session.add_all([role, resource])
        await session.commit()

        # Create role-resource and user-role mappings
        role_resource = RoleResource(role_id=role_id, resource_id=resource_id)
        user_role = UserRole(user_id=test_user_id, role_id=role_id)
        session.add_all([role_resource, user_role])
        await session.commit()

    # Should succeed for first-time user even with feature enabled
    response = test_client.post(
        '/floware/v1/authenticate',
        json={'email': 'firsttime_test@example.com', 'password': 'test_password'},
    )

    assert response.status_code == 200
    assert response.json()['data']['user']['access_token'] == 'mock_token'


@pytest.mark.asyncio
async def test_authenticate_inactive_account_feature_enabled_within_threshold(
    test_client, test_session: AsyncSession, test_user_id, monkeypatch, mock_config
):
    """Test that active users within threshold can login when feature is enabled"""
    # Get threshold from config (same config that service uses)
    threshold_days = int(mock_config['auth']['inactive_days_threshold'])

    # Mock the feature flag to be enabled
    def mock_is_feature_enabled(feature: str) -> bool:
        if feature == 'INACTIVE_ACCOUNT_DISABLE_FLAG':
            return True
        return False

    monkeypatch.setattr(
        'common_module.feature.feature_flag.is_feature_enabled', mock_is_feature_enabled
    )
    monkeypatch.setattr(
        'user_management_module.controllers.auth_controller.is_feature_enabled',
        mock_is_feature_enabled,
    )

    # Create test IDs
    role_id = str(uuid4())
    resource_id = str(uuid4())
    hashed_password = hash_password('test_password')

    # Create user active within threshold (threshold - 30 days ago)
    recent_date = datetime.now(timezone.utc) - timedelta(days=threshold_days - 30)

    async with test_session() as session:
        # Create user with recent last_login_at
        user = User(
            id=test_user_id,
            email='active_test@example.com',
            password=hashed_password,
            first_name='Active',
            last_name='User',
            last_login_at=recent_date,
        )
        session.add(user)
        await session.commit()

        # Create role and resource setup for console access
        role = Role(id=role_id, name='Test Role')
        resource = Resource(
            id=resource_id,
            key='console_resource',
            value='test_resource',
            scope=ResourceScope.CONSOLE,
        )
        session.add_all([role, resource])
        await session.commit()

        # Create role-resource and user-role mappings
        role_resource = RoleResource(role_id=role_id, resource_id=resource_id)
        user_role = UserRole(user_id=test_user_id, role_id=role_id)
        session.add_all([role_resource, user_role])
        await session.commit()

    # Should succeed for active user within threshold
    response = test_client.post(
        '/floware/v1/authenticate',
        json={'email': 'active_test@example.com', 'password': 'test_password'},
    )

    assert response.status_code == 200
    assert response.json()['data']['user']['access_token'] == 'mock_token'


@pytest.mark.asyncio
async def test_authenticate_inactive_account_feature_enabled_over_threshold(
    test_client, test_session: AsyncSession, test_user_id, monkeypatch, mock_config
):
    """Test that inactive users over threshold are rejected when feature is enabled"""
    # Get threshold from config (same config that service uses)
    threshold_days = int(mock_config['auth']['inactive_days_threshold'])

    # Mock the feature flag to be enabled
    def mock_is_feature_enabled(feature: str) -> bool:
        if feature == 'INACTIVE_ACCOUNT_DISABLE_FLAG':
            return True
        return False

    monkeypatch.setattr(
        'common_module.feature.feature_flag.is_feature_enabled', mock_is_feature_enabled
    )
    monkeypatch.setattr(
        'user_management_module.controllers.auth_controller.is_feature_enabled',
        mock_is_feature_enabled,
    )

    # Create test IDs
    role_id = str(uuid4())
    resource_id = str(uuid4())
    hashed_password = hash_password('test_password')

    # Create user inactive for (threshold + 30) days - clearly over threshold
    inactive_date = datetime.now(timezone.utc) - timedelta(days=threshold_days + 30)

    async with test_session() as session:
        # Create user with old last_login_at
        user = User(
            id=test_user_id,
            email='very_inactive_test@example.com',
            password=hashed_password,
            first_name='VeryInactive',
            last_name='User',
            last_login_at=inactive_date,
        )
        session.add(user)
        await session.commit()

        # Create role and resource setup for console access
        role = Role(id=role_id, name='Test Role')
        resource = Resource(
            id=resource_id,
            key='console_resource',
            value='test_resource',
            scope=ResourceScope.CONSOLE,
        )
        session.add_all([role, resource])
        await session.commit()

        # Create role-resource and user-role mappings
        role_resource = RoleResource(role_id=role_id, resource_id=resource_id)
        user_role = UserRole(user_id=test_user_id, role_id=role_id)
        session.add_all([role_resource, user_role])
        await session.commit()

    # Should be rejected due to inactivity
    response = test_client.post(
        '/floware/v1/authenticate',
        json={'email': 'very_inactive_test@example.com', 'password': 'test_password'},
    )

    assert response.status_code == 403
    assert 'disabled due to inactivity' in response.json()['meta']['error']
    assert 'days ago' in response.json()['meta']['error']


@pytest.mark.asyncio
async def test_authenticate_updates_last_login_timestamp(
    test_client, test_session: AsyncSession, test_user_id
):
    """Test that successful login updates user's last_login_at timestamp"""
    # Create test IDs
    role_id = str(uuid4())
    resource_id = str(uuid4())
    hashed_password = hash_password('test_password')

    # Create user with old last_login_at timestamp
    old_login_date = datetime.now(timezone.utc) - timedelta(days=10)

    async with test_session() as session:
        # Create user with old last_login_at
        user = User(
            id=test_user_id,
            email='update_timestamp_test@example.com',
            password=hashed_password,
            first_name='Update',
            last_name='User',
            last_login_at=old_login_date,
        )
        session.add(user)
        await session.commit()

        # Create role and resource setup for console access
        role = Role(id=role_id, name='Test Role')
        resource = Resource(
            id=resource_id,
            key='console_resource',
            value='test_resource',
            scope=ResourceScope.CONSOLE,
        )
        session.add_all([role, resource])
        await session.commit()

        # Create role-resource and user-role mappings
        role_resource = RoleResource(role_id=role_id, resource_id=resource_id)
        user_role = UserRole(user_id=test_user_id, role_id=role_id)
        session.add_all([role_resource, user_role])
        await session.commit()

    # Perform successful authentication
    response = test_client.post(
        '/floware/v1/authenticate',
        json={
            'email': 'update_timestamp_test@example.com',
            'password': 'test_password',
        },
    )

    assert response.status_code == 200
    assert response.json()['data']['user']['access_token'] == 'mock_token'

    # Verify last_login_at was updated in database
    async with test_session() as session:
        updated_user = await session.get(User, test_user_id)
        assert updated_user.last_login_at is not None

        # Handle timezone-aware/naive datetime comparison for both timestamps
        updated_login_time = updated_user.last_login_at
        if updated_login_time.tzinfo is None:
            updated_login_time = updated_login_time.replace(tzinfo=timezone.utc)

        old_login_time = old_login_date
        if old_login_time.tzinfo is None:
            old_login_time = old_login_time.replace(tzinfo=timezone.utc)

        # Verify the timestamp was updated (should be more recent than the old timestamp)
        assert updated_login_time > old_login_time


@pytest.mark.asyncio
async def test_authenticate_inactive_account_with_wrong_password(
    test_client, test_session: AsyncSession, test_user_id, monkeypatch, mock_config
):
    """Test that inactivity error takes precedence over wrong password error"""
    # Get threshold from config (same config that service uses)
    threshold_days = int(mock_config['auth']['inactive_days_threshold'])

    # Mock the feature flag to be enabled
    def mock_is_feature_enabled(feature: str) -> bool:
        if feature == 'INACTIVE_ACCOUNT_DISABLE_FLAG':
            return True
        return False

    monkeypatch.setattr(
        'common_module.feature.feature_flag.is_feature_enabled', mock_is_feature_enabled
    )
    monkeypatch.setattr(
        'user_management_module.controllers.auth_controller.is_feature_enabled',
        mock_is_feature_enabled,
    )

    # Create test IDs
    role_id = str(uuid4())
    resource_id = str(uuid4())
    hashed_password = hash_password('correct_password')

    # Create user inactive for (threshold + 30) days
    inactive_date = datetime.now(timezone.utc) - timedelta(days=threshold_days + 30)

    async with test_session() as session:
        # Create inactive user
        user = User(
            id=test_user_id,
            email='inactive_wrong_pwd_test@example.com',
            password=hashed_password,
            first_name='InactiveWrong',
            last_name='User',
            last_login_at=inactive_date,
        )
        session.add(user)
        await session.commit()

        # Create role and resource setup for console access
        role = Role(id=role_id, name='Test Role')
        resource = Resource(
            id=resource_id,
            key='console_resource',
            value='test_resource',
            scope=ResourceScope.CONSOLE,
        )
        session.add_all([role, resource])
        await session.commit()

        # Create role-resource and user-role mappings
        role_resource = RoleResource(role_id=role_id, resource_id=resource_id)
        user_role = UserRole(user_id=test_user_id, role_id=role_id)
        session.add_all([role_resource, user_role])
        await session.commit()

    # Use wrong password - should show inactivity error, not wrong password error
    response = test_client.post(
        '/floware/v1/authenticate',
        json={
            'email': 'inactive_wrong_pwd_test@example.com',
            'password': 'wrong_password',
        },
    )

    assert response.status_code == 403
    assert 'disabled due to inactivity' in response.json()['meta']['error']
    # Should NOT show "Incorrect username or password"
    assert 'Incorrect username or password' not in response.json()['meta']['error']


@pytest.mark.asyncio
async def test_authenticate_inactive_account_with_lockout(
    test_client, test_session: AsyncSession, test_user_id, monkeypatch, mock_config
):
    """Test that lockout error takes precedence over inactivity error"""
    # Get threshold from config (same config that service uses)
    threshold_days = int(mock_config['auth']['inactive_days_threshold'])

    # Mock the feature flag to be enabled
    def mock_is_feature_enabled(feature: str) -> bool:
        if feature == 'INACTIVE_ACCOUNT_DISABLE_FLAG':
            return True
        return False

    monkeypatch.setattr(
        'common_module.feature.feature_flag.is_feature_enabled', mock_is_feature_enabled
    )
    monkeypatch.setattr(
        'user_management_module.controllers.auth_controller.is_feature_enabled',
        mock_is_feature_enabled,
    )

    # Get max failed attempts from environment variable, default to 3
    max_failed_attempts = int(os.getenv('MAX_FAILED_ATTEMPTS', 3))

    hashed_password = hash_password('test_password')
    current_time = datetime.now(timezone.utc)

    # Create user both inactive (threshold + 30 days) AND locked
    inactive_date = current_time - timedelta(days=threshold_days + 30)
    locked_until = current_time + timedelta(hours=1)

    async with test_session() as session:
        # Create user that is both inactive and locked
        user = User(
            id=test_user_id,
            email='inactive_locked_test@example.com',
            password=hashed_password,
            first_name='InactiveLocked',
            last_name='User',
            last_login_at=inactive_date,
            failed_attempts=max_failed_attempts,
            locked_until=locked_until,
            last_failed_attempt=current_time,
        )
        session.add(user)
        await session.commit()

    # Should show lockout error first, not inactivity error
    response = test_client.post(
        '/floware/v1/authenticate',
        json={'email': 'inactive_locked_test@example.com', 'password': 'test_password'},
    )

    assert response.status_code == 423  # 423 for locked accounts
    assert 'Account locked' in response.json()['meta']['error']
    # Should NOT show inactivity error when user is also locked
    assert 'disabled due to inactivity' not in response.json()['meta']['error']
