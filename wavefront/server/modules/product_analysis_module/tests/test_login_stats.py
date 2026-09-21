from datetime import datetime
from uuid import UUID
from uuid import uuid4

from db_repo_module.models.product_analytics import ProductAnalytics
from db_repo_module.models.session import Session
from db_repo_module.models.user import User
from db_repo_module.models.user_group import UserGroup
from db_repo_module.models.user_group_member import UserGroupMember
import pytest
from sqlalchemy.ext.asyncio import AsyncSession


LOGIN_STATS_PARAMS = {
    'start_date': '2025-01-01',
    'end_date': '2025-02-01',
}


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


async def create_auth_session(
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    *,
    email: str = 'caller@example.com',
):
    user_id = _as_uuid(test_user_id)
    async with test_session() as session:
        if await session.get(User, user_id) is None:
            session.add(
                User(
                    id=user_id,
                    email=email,
                    password='hashed',
                    first_name='Caller',
                    last_name='User',
                )
            )
        session.add(
            Session(
                id=_as_uuid(test_session_id),
                user_id=user_id,
                device_info='test_device',
            )
        )
        await session.commit()


async def seed_login_stats_fixture(test_session: AsyncSession, manager_user_id: str):
    """Manager in group A; users in A, B, and neither, each with one login."""
    manager_id = _as_uuid(manager_user_id)
    group_a_id = uuid4()
    group_b_id = uuid4()
    user_in_a_id = uuid4()
    user_in_b_id = uuid4()
    user_ungrouped_id = uuid4()
    login_at = datetime(2025, 1, 15, 12, 0, 0)

    users = [
        User(
            id=manager_id,
            email='manager@example.com',
            password='hashed',
            first_name='Mgr',
            last_name='User',
        ),
        User(
            id=user_in_a_id,
            email='in-a@example.com',
            password='hashed',
            first_name='In',
            last_name='A',
        ),
        User(
            id=user_in_b_id,
            email='in-b@example.com',
            password='hashed',
            first_name='In',
            last_name='B',
        ),
        User(
            id=user_ungrouped_id,
            email='ungrouped@example.com',
            password='hashed',
            first_name='No',
            last_name='Group',
        ),
    ]
    groups = [
        UserGroup(id=group_a_id, name=f'group-a-{str(group_a_id)[:8]}'),
        UserGroup(id=group_b_id, name=f'group-b-{str(group_b_id)[:8]}'),
    ]
    memberships = [
        UserGroupMember(group_id=group_a_id, user_id=manager_id),
        UserGroupMember(group_id=group_a_id, user_id=user_in_a_id),
        UserGroupMember(group_id=group_b_id, user_id=user_in_b_id),
    ]
    logins = [
        ProductAnalytics(
            event_name='user_login',
            page='login',
            page_path='/login',
            user_id=user_id,
            session_id=uuid4(),
            user_role='viewer',
            created_at=login_at,
        )
        for user_id in (user_in_a_id, user_in_b_id, user_ungrouped_id)
    ]

    async with test_session() as session:
        session.add_all(users)
        session.add_all(groups)
        await session.flush()
        session.add_all(memberships)
        session.add_all(logins)
        await session.commit()

    return {
        'group_a_id': str(group_a_id),
        'group_b_id': str(group_b_id),
    }


def _emails(login_stats: list[dict]) -> set[str]:
    return {row['email'] for row in login_stats}


@pytest.mark.asyncio
async def test_login_stats_denied_for_non_admin_non_manager(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    auth_token,
    mock_non_admin_functions,
):
    await create_auth_session(test_session, test_user_id, test_session_id)
    headers = {'Authorization': f'Bearer {auth_token}'}

    summary = test_client.get(
        '/floware/v1/product-analysis/stats/login/summary',
        params=LOGIN_STATS_PARAMS,
        headers=headers,
    )
    listing = test_client.get(
        '/floware/v1/product-analysis/stats/login',
        params=LOGIN_STATS_PARAMS,
        headers=headers,
    )

    assert summary.status_code == 403
    assert listing.status_code == 403


@pytest.mark.asyncio
async def test_login_stats_rejects_invalid_date_range(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    auth_token,
    mock_admin_functions,
):
    await create_auth_session(test_session, test_user_id, test_session_id)
    headers = {'Authorization': f'Bearer {auth_token}'}

    inverted = test_client.get(
        '/floware/v1/product-analysis/stats/login/summary',
        params={'start_date': '2025-02-01', 'end_date': '2025-01-01'},
        headers=headers,
    )
    too_wide = test_client.get(
        '/floware/v1/product-analysis/stats/login',
        params={'start_date': '2024-01-01', 'end_date': '2026-01-01'},
        headers=headers,
    )

    assert inverted.status_code == 400
    assert too_wide.status_code == 400


@pytest.mark.asyncio
async def test_login_stats_admin_sees_all_users(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    auth_token,
    mock_admin_functions,
):
    await seed_login_stats_fixture(test_session, test_user_id)
    await create_auth_session(test_session, test_user_id, test_session_id)
    headers = {'Authorization': f'Bearer {auth_token}'}

    summary = test_client.get(
        '/floware/v1/product-analysis/stats/login/summary',
        params=LOGIN_STATS_PARAMS,
        headers=headers,
    )
    listing = test_client.get(
        '/floware/v1/product-analysis/stats/login',
        params=LOGIN_STATS_PARAMS,
        headers=headers,
    )

    assert summary.status_code == 200
    assert listing.status_code == 200
    summary_data = summary.json()['data']
    # manager + in-a + in-b + ungrouped
    assert summary_data['total_users'] == 4
    assert summary_data['active_users'] == 3
    assert _emails(listing.json()['data']['login_stats']) == {
        'manager@example.com',
        'in-a@example.com',
        'in-b@example.com',
        'ungrouped@example.com',
    }


@pytest.mark.asyncio
async def test_login_stats_admin_can_filter_by_any_group(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    auth_token,
    mock_admin_functions,
):
    fixture = await seed_login_stats_fixture(test_session, test_user_id)
    await create_auth_session(test_session, test_user_id, test_session_id)
    headers = {'Authorization': f'Bearer {auth_token}'}
    params = {**LOGIN_STATS_PARAMS, 'group_id': fixture['group_b_id']}

    summary = test_client.get(
        '/floware/v1/product-analysis/stats/login/summary',
        params=params,
        headers=headers,
    )
    listing = test_client.get(
        '/floware/v1/product-analysis/stats/login',
        params=params,
        headers=headers,
    )

    assert summary.status_code == 200
    assert listing.status_code == 200
    assert summary.json()['data']['total_users'] == 1
    assert _emails(listing.json()['data']['login_stats']) == {'in-b@example.com'}


@pytest.mark.asyncio
async def test_login_stats_manager_sees_only_accessible_groups(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    auth_token,
    mock_manager_functions,
):
    await seed_login_stats_fixture(test_session, test_user_id)
    await create_auth_session(test_session, test_user_id, test_session_id)
    headers = {'Authorization': f'Bearer {auth_token}'}

    summary = test_client.get(
        '/floware/v1/product-analysis/stats/login/summary',
        params=LOGIN_STATS_PARAMS,
        headers=headers,
    )
    listing = test_client.get(
        '/floware/v1/product-analysis/stats/login',
        params=LOGIN_STATS_PARAMS,
        headers=headers,
    )

    assert summary.status_code == 200
    assert listing.status_code == 200
    # group A only: manager + in-a
    assert summary.json()['data']['total_users'] == 2
    assert _emails(listing.json()['data']['login_stats']) == {
        'manager@example.com',
        'in-a@example.com',
    }


@pytest.mark.asyncio
async def test_login_stats_manager_can_filter_to_own_group(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    auth_token,
    mock_manager_functions,
):
    fixture = await seed_login_stats_fixture(test_session, test_user_id)
    await create_auth_session(test_session, test_user_id, test_session_id)
    headers = {'Authorization': f'Bearer {auth_token}'}
    params = {**LOGIN_STATS_PARAMS, 'group_id': fixture['group_a_id']}

    listing = test_client.get(
        '/floware/v1/product-analysis/stats/login',
        params=params,
        headers=headers,
    )
    summary = test_client.get(
        '/floware/v1/product-analysis/stats/login/summary',
        params=params,
        headers=headers,
    )

    assert listing.status_code == 200
    assert summary.status_code == 200
    assert summary.json()['data']['total_users'] == 2
    assert _emails(listing.json()['data']['login_stats']) == {
        'manager@example.com',
        'in-a@example.com',
    }


@pytest.mark.asyncio
async def test_login_stats_manager_denied_for_other_group(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    auth_token,
    mock_manager_functions,
):
    fixture = await seed_login_stats_fixture(test_session, test_user_id)
    await create_auth_session(test_session, test_user_id, test_session_id)
    headers = {'Authorization': f'Bearer {auth_token}'}
    params = {**LOGIN_STATS_PARAMS, 'group_id': fixture['group_b_id']}

    summary = test_client.get(
        '/floware/v1/product-analysis/stats/login/summary',
        params=params,
        headers=headers,
    )
    listing = test_client.get(
        '/floware/v1/product-analysis/stats/login',
        params=params,
        headers=headers,
    )

    assert summary.status_code == 403
    assert listing.status_code == 403


@pytest.mark.asyncio
async def test_login_stats_manager_with_no_groups_sees_nobody(
    test_client,
    test_session: AsyncSession,
    test_user_id,
    test_session_id,
    auth_token,
    mock_manager_functions,
):
    other_id = uuid4()
    async with test_session() as session:
        session.add_all(
            [
                User(
                    id=other_id,
                    email='other@example.com',
                    password='hashed',
                    first_name='Other',
                    last_name='User',
                ),
                ProductAnalytics(
                    event_name='user_login',
                    page='login',
                    page_path='/login',
                    user_id=other_id,
                    session_id=uuid4(),
                    user_role='viewer',
                    created_at=datetime(2025, 1, 15, 12, 0, 0),
                ),
            ]
        )
        await session.commit()
    await create_auth_session(
        test_session, test_user_id, test_session_id, email='manager@example.com'
    )

    headers = {'Authorization': f'Bearer {auth_token}'}
    summary = test_client.get(
        '/floware/v1/product-analysis/stats/login/summary',
        params=LOGIN_STATS_PARAMS,
        headers=headers,
    )
    listing = test_client.get(
        '/floware/v1/product-analysis/stats/login',
        params=LOGIN_STATS_PARAMS,
        headers=headers,
    )

    assert summary.status_code == 200
    assert listing.status_code == 200
    assert summary.json()['data']['total_users'] == 0
    assert listing.json()['data']['login_stats'] == []
    assert listing.json()['data']['total'] == 0
