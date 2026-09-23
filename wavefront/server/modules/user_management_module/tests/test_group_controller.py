"""Tests for user groups.

Empty groups get deliberate coverage throughout: a group with no roles and a
user with no direct roles are both legitimate states, and both are the kind of
thing an inner join or an over-eager validator silently drops.
"""

import uuid

from db_repo_module.models.resource import Resource
from db_repo_module.models.resource import ResourceScope
from db_repo_module.models.role import Role
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.models.user import User
from db_repo_module.models.user_group import UserGroup
from db_repo_module.models.user_group_member import UserGroupMember
from db_repo_module.models.user_group_role import UserGroupRole
from db_repo_module.models.user_role import UserRole
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from flo_testing import seed_user_session as create_session

# The test_session fixture hands out a session factory, not a live session.
SessionFactory = async_sessionmaker[AsyncSession]


async def create_role_with_resource(
    test_session: SessionFactory,
    role_id: str,
    role_name: str,
    scope: ResourceScope = ResourceScope.CONSOLE,
    resource_key: str = 'console_access',
    resource_value: str = 'true',
) -> str:
    """Create a role linked to a single resource, returning the resource id."""
    async with test_session() as session:
        resource = Resource(
            key=resource_key,
            value=resource_value,
            description=f'{scope} resource',
            scope=scope,
        )
        session.add(resource)
        await session.flush()
        resource_id = resource.id

        role = Role(id=role_id, name=role_name)
        session.add(role)
        await session.flush()

        session.add(RoleResource(role_id=role.id, resource_id=resource_id))
        await session.commit()
    return str(resource_id)


async def create_group(
    test_session: SessionFactory,
    name: str,
    role_ids: list[str] | None = None,
    user_ids: list[str] | None = None,
) -> str:
    async with test_session() as session:
        group = UserGroup(id=uuid.uuid4(), name=name, description=f'{name} group')
        session.add(group)
        await session.flush()
        group_id = group.id

        session.add_all(
            [
                UserGroupRole(group_id=group_id, role_id=role_id)
                for role_id in (role_ids or [])
            ]
        )
        session.add_all(
            [
                UserGroupMember(group_id=group_id, user_id=user_id)
                for user_id in (user_ids or [])
            ]
        )
        await session.commit()
    return str(group_id)


async def create_user(test_session: SessionFactory, email: str) -> str:
    async with test_session() as session:
        user = User(
            email=email,
            password='hashedpassword',
            first_name='Group',
            last_name='Member',
        )
        session.add(user)
        await session.flush()
        user_id = str(user.id)
        await session.commit()
    return user_id


def auth_headers(auth_token):
    return {'Authorization': f'Bearer {auth_token}'}


# --------------------------------------------------------------------------
# Group CRUD
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_group_with_roles_and_members(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_group_admin_functions,
):
    await create_session(test_session, test_user_id, test_session_id)
    await create_role_with_resource(test_session, 'role_a', 'Role A')
    member_id = await create_user(test_session, 'member@example.com')

    response = test_client.post(
        '/floware/v1/groups',
        json={
            'name': 'Engineering',
            'description': 'Eng team',
            'role_ids': ['role_a'],
            'user_ids': [member_id],
        },
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 201
    group_id = response.json()['data']['group_id']

    async with test_session() as session:
        roles = (
            await session.scalars(
                select(UserGroupRole.role_id).where(UserGroupRole.group_id == group_id)
            )
        ).all()
        members = (
            await session.scalars(
                select(UserGroupMember.user_id).where(
                    UserGroupMember.group_id == group_id
                )
            )
        ).all()
    assert [str(r) for r in roles] == ['role_a']
    assert [str(m) for m in members] == [member_id]


@pytest.mark.asyncio
async def test_create_group_without_roles_or_members(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_group_admin_functions,
):
    """A name is enough. An empty group is a valid starting state."""
    await create_session(test_session, test_user_id, test_session_id)

    response = test_client.post(
        '/floware/v1/groups',
        json={'name': 'Empty Group'},
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 201

    group_id = response.json()['data']['group_id']
    async with test_session() as session:
        group = await session.get(UserGroup, uuid.UUID(group_id))
        assert group is not None
        roles = (
            await session.scalars(
                select(UserGroupRole).where(UserGroupRole.group_id == group_id)
            )
        ).all()
    assert roles == []


@pytest.mark.asyncio
async def test_create_group_rejects_duplicate_name(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_group_admin_functions,
):
    await create_session(test_session, test_user_id, test_session_id)
    await create_group(test_session, 'Duplicate')

    response = test_client.post(
        '/floware/v1/groups',
        json={'name': 'Duplicate'},
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 400
    assert 'already exists' in str(response.json())


@pytest.mark.asyncio
async def test_create_group_rejects_unknown_role(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_group_admin_functions,
):
    await create_session(test_session, test_user_id, test_session_id)

    response = test_client.post(
        '/floware/v1/groups',
        json={'name': 'Bad Roles', 'role_ids': ['does_not_exist']},
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 400
    assert 'Invalid role IDs' in str(response.json())


@pytest.mark.asyncio
async def test_list_groups_includes_empty_group_with_zero_counts(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_group_admin_functions,
):
    """The regression an inner join would cause: the just-created, still-empty
    group is exactly the one an admin needs to see in order to configure it."""
    await create_session(test_session, test_user_id, test_session_id)
    await create_role_with_resource(test_session, 'role_a', 'Role A')
    member_id = await create_user(test_session, 'member@example.com')
    await create_group(test_session, 'Populated', ['role_a'], [member_id])
    await create_group(test_session, 'Totally Empty')

    response = test_client.get('/floware/v1/groups', headers=auth_headers(auth_token))
    assert response.status_code == 200

    data = response.json()['data']
    assert data['total'] == 2
    by_name = {g['name']: g for g in data['groups']}
    assert set(by_name) == {'Populated', 'Totally Empty'}

    assert by_name['Populated']['role_count'] == 1
    assert by_name['Populated']['member_count'] == 1
    assert by_name['Totally Empty']['role_count'] == 0
    assert by_name['Totally Empty']['member_count'] == 0


@pytest.mark.asyncio
async def test_get_group_detail_empty_group_returns_empty_lists(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_group_admin_functions,
):
    await create_session(test_session, test_user_id, test_session_id)
    group_id = await create_group(test_session, 'Empty Detail')

    response = test_client.get(
        f'/floware/v1/groups/{group_id}', headers=auth_headers(auth_token)
    )
    assert response.status_code == 200

    group = response.json()['data']['group']
    assert group['name'] == 'Empty Detail'
    assert group['roles'] == []
    assert group['users'] == []


@pytest.mark.asyncio
async def test_get_group_not_found(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_group_admin_functions,
):
    await create_session(test_session, test_user_id, test_session_id)

    response = test_client.get(
        f'/floware/v1/groups/{uuid.uuid4()}', headers=auth_headers(auth_token)
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_group_replaces_roles(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_group_admin_functions,
):
    await create_session(test_session, test_user_id, test_session_id)
    await create_role_with_resource(test_session, 'role_a', 'Role A')
    await create_role_with_resource(
        test_session, 'role_b', 'Role B', resource_key='other', resource_value='b'
    )
    group_id = await create_group(test_session, 'Swap Roles', ['role_a'])

    response = test_client.patch(
        f'/floware/v1/groups/{group_id}',
        json={'name': 'Renamed', 'role_ids': ['role_b']},
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 200

    async with test_session() as session:
        roles = (
            await session.scalars(
                select(UserGroupRole.role_id).where(UserGroupRole.group_id == group_id)
            )
        ).all()
        group = await session.get(UserGroup, uuid.UUID(group_id))
    assert [str(r) for r in roles] == ['role_b']
    assert group.name == 'Renamed'


@pytest.mark.asyncio
async def test_update_group_with_empty_role_list_strips_all_roles(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_group_admin_functions,
):
    """[] means "remove every role" -- distinct from None, which means "leave
    roles alone". Treating it as a no-op would make emptying a group
    impossible."""
    await create_session(test_session, test_user_id, test_session_id)
    await create_role_with_resource(test_session, 'role_a', 'Role A')
    group_id = await create_group(test_session, 'To Be Emptied', ['role_a'])

    response = test_client.patch(
        f'/floware/v1/groups/{group_id}',
        json={'role_ids': []},
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 200

    async with test_session() as session:
        roles = (
            await session.scalars(
                select(UserGroupRole).where(UserGroupRole.group_id == group_id)
            )
        ).all()
    assert roles == []


@pytest.mark.asyncio
async def test_update_group_without_role_ids_leaves_roles_untouched(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_group_admin_functions,
):
    """The other half of the None/[] distinction."""
    await create_session(test_session, test_user_id, test_session_id)
    await create_role_with_resource(test_session, 'role_a', 'Role A')
    group_id = await create_group(test_session, 'Keep Roles', ['role_a'])

    response = test_client.patch(
        f'/floware/v1/groups/{group_id}',
        json={'description': 'just a description change'},
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 200

    async with test_session() as session:
        roles = (
            await session.scalars(
                select(UserGroupRole.role_id).where(UserGroupRole.group_id == group_id)
            )
        ).all()
    assert [str(r) for r in roles] == ['role_a']


@pytest.mark.asyncio
async def test_delete_group_keeps_members_direct_roles(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_group_admin_functions,
):
    await create_session(test_session, test_user_id, test_session_id)
    await create_role_with_resource(test_session, 'role_a', 'Role A')
    member_id = await create_user(test_session, 'member@example.com')

    async with test_session() as session:
        session.add(UserRole(user_id=member_id, role_id='role_a'))
        await session.commit()

    group_id = await create_group(test_session, 'Doomed', ['role_a'], [member_id])

    response = test_client.delete(
        f'/floware/v1/groups/{group_id}', headers=auth_headers(auth_token)
    )
    assert response.status_code == 200

    async with test_session() as session:
        assert await session.get(UserGroup, uuid.UUID(group_id)) is None
        memberships = (
            await session.scalars(
                select(UserGroupMember).where(UserGroupMember.group_id == group_id)
            )
        ).all()
        direct_roles = (
            await session.scalars(
                select(UserRole.role_id).where(UserRole.user_id == member_id)
            )
        ).all()
    assert memberships == []
    assert [str(r) for r in direct_roles] == ['role_a']


# --------------------------------------------------------------------------
# Membership
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_and_remove_group_members(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_group_admin_functions,
):
    await create_session(test_session, test_user_id, test_session_id)
    group_id = await create_group(test_session, 'Membership')
    member_id = await create_user(test_session, 'member@example.com')

    response = test_client.post(
        f'/floware/v1/groups/{group_id}/members',
        json={'user_ids': [member_id]},
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 200

    async with test_session() as session:
        members = (
            await session.scalars(
                select(UserGroupMember.user_id).where(
                    UserGroupMember.group_id == group_id
                )
            )
        ).all()
    assert [str(m) for m in members] == [member_id]

    response = test_client.request(
        'DELETE',
        f'/floware/v1/groups/{group_id}/members',
        json={'user_ids': [member_id]},
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 200

    async with test_session() as session:
        members = (
            await session.scalars(
                select(UserGroupMember).where(UserGroupMember.group_id == group_id)
            )
        ).all()
    assert members == []


@pytest.mark.asyncio
async def test_add_group_member_is_idempotent(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_group_admin_functions,
):
    """Re-adding an existing member must not violate the composite primary key."""
    await create_session(test_session, test_user_id, test_session_id)
    member_id = await create_user(test_session, 'member@example.com')
    group_id = await create_group(test_session, 'Idempotent', None, [member_id])

    response = test_client.post(
        f'/floware/v1/groups/{group_id}/members',
        json={'user_ids': [member_id]},
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 200

    async with test_session() as session:
        members = (
            await session.scalars(
                select(UserGroupMember).where(UserGroupMember.group_id == group_id)
            )
        ).all()
    assert len(members) == 1


@pytest.mark.asyncio
async def test_get_user_groups(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_auth_admin_user_functions,
):
    await create_session(test_session, test_user_id, test_session_id)
    member_id = await create_user(test_session, 'member@example.com')
    await create_group(test_session, 'Alpha', None, [member_id])
    await create_group(test_session, 'Beta', None, [member_id])

    response = test_client.get(
        f'/floware/v1/users/{member_id}/groups', headers=auth_headers(auth_token)
    )
    assert response.status_code == 200

    names = [g['name'] for g in response.json()['data']['groups']]
    assert names == ['Alpha', 'Beta']


@pytest.mark.asyncio
async def test_get_user_groups_empty_for_user_in_no_groups(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_auth_admin_user_functions,
):
    await create_session(test_session, test_user_id, test_session_id)
    member_id = await create_user(test_session, 'lonely@example.com')

    response = test_client.get(
        f'/floware/v1/users/{member_id}/groups', headers=auth_headers(auth_token)
    )
    assert response.status_code == 200
    assert response.json()['data']['groups'] == []


# --------------------------------------------------------------------------
# Authorization
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_group_endpoints_reject_non_admin(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_group_non_admin_functions,
):
    await create_session(test_session, test_user_id, test_session_id)
    group_id = await create_group(test_session, 'Private')

    get_response = test_client.get(
        '/floware/v1/groups', headers=auth_headers(auth_token)
    )
    assert get_response.status_code == 401

    post_response = test_client.post(
        '/floware/v1/groups',
        json={'name': 'Nope'},
        headers=auth_headers(auth_token),
    )
    assert post_response.status_code == 401

    patch_response = test_client.patch(
        f'/floware/v1/groups/{group_id}',
        json={'name': 'Nope'},
        headers=auth_headers(auth_token),
    )
    assert patch_response.status_code == 401

    delete_response = test_client.delete(
        f'/floware/v1/groups/{group_id}', headers=auth_headers(auth_token)
    )
    assert delete_response.status_code == 401


# --------------------------------------------------------------------------
# Last-admin guard on group mutations
#
# A group can be the only source of the admin role, so stripping its roles,
# deleting it, or removing its last member can demote the final admin and lock
# everyone out of the instance.
# --------------------------------------------------------------------------


async def setup_group_only_admin(test_session) -> tuple[str, str]:
    """An instance whose single admin holds the role solely through a group."""
    await create_role_with_resource(test_session, 'admin_role', 'admin')
    admin_id = await create_user(test_session, 'groupadmin@example.com')
    group_id = await create_group(test_session, 'Admins', ['admin_role'], [admin_id])
    return group_id, admin_id


@pytest.mark.asyncio
async def test_update_group_cannot_strip_last_admin_role(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_group_admin_functions,
):
    await create_session(test_session, test_user_id, test_session_id)
    group_id, _ = await setup_group_only_admin(test_session)

    response = test_client.patch(
        f'/floware/v1/groups/{group_id}',
        json={'role_ids': []},
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 400
    assert 'admin' in str(response.json()).lower()

    async with test_session() as session:
        roles = (
            await session.scalars(
                select(UserGroupRole.role_id).where(UserGroupRole.group_id == group_id)
            )
        ).all()
    assert [str(r) for r in roles] == ['admin_role']


@pytest.mark.asyncio
async def test_delete_group_cannot_remove_last_admin(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_group_admin_functions,
):
    await create_session(test_session, test_user_id, test_session_id)
    group_id, _ = await setup_group_only_admin(test_session)

    response = test_client.delete(
        f'/floware/v1/groups/{group_id}', headers=auth_headers(auth_token)
    )
    assert response.status_code == 400
    assert 'admin' in str(response.json()).lower()

    async with test_session() as session:
        assert await session.get(UserGroup, uuid.UUID(group_id)) is not None


@pytest.mark.asyncio
async def test_remove_members_cannot_remove_last_admin(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_group_admin_functions,
):
    await create_session(test_session, test_user_id, test_session_id)
    group_id, admin_id = await setup_group_only_admin(test_session)

    response = test_client.request(
        'DELETE',
        f'/floware/v1/groups/{group_id}/members',
        json={'user_ids': [admin_id]},
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 400
    assert 'admin' in str(response.json()).lower()

    async with test_session() as session:
        members = (
            await session.scalars(
                select(UserGroupMember.user_id).where(
                    UserGroupMember.group_id == group_id
                )
            )
        ).all()
    assert [str(m) for m in members] == [admin_id]


@pytest.mark.asyncio
async def test_group_mutations_allowed_when_another_admin_remains(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_group_admin_functions,
):
    """The guard blocks only the last admin, not admin management in general."""
    await create_session(test_session, test_user_id, test_session_id)
    group_id, _ = await setup_group_only_admin(test_session)

    direct_admin = await create_user(test_session, 'directadmin@example.com')
    async with test_session() as session:
        session.add(UserRole(user_id=direct_admin, role_id='admin_role'))
        await session.commit()

    response = test_client.delete(
        f'/floware/v1/groups/{group_id}', headers=auth_headers(auth_token)
    )
    assert response.status_code == 200

    async with test_session() as session:
        assert await session.get(UserGroup, uuid.UUID(group_id)) is None


@pytest.mark.asyncio
async def test_delete_role_less_group_is_unaffected_by_admin_guard(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_group_admin_functions,
):
    """A group granting no admin is deletable even with no admins anywhere."""
    await create_session(test_session, test_user_id, test_session_id)
    group_id = await create_group(test_session, 'Harmless')

    response = test_client.delete(
        f'/floware/v1/groups/{group_id}', headers=auth_headers(auth_token)
    )
    assert response.status_code == 200


# --------------------------------------------------------------------------
# Effective roles: the union of direct and group-granted roles
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_group_grants_resources_to_member(
    test_session,
    setup_containers,
):
    """A user with no direct roles reaches resources through their group."""
    _, _, user_container = setup_containers
    user_service = user_container.user_service()

    await create_role_with_resource(
        test_session,
        'dash_role',
        'Dashboard Role',
        scope=ResourceScope.DASHBOARD,
        resource_key='sales',
        resource_value='dashboard',
    )
    member_id = await create_user(test_session, 'groupmember@example.com')
    await create_group(test_session, 'Dash Group', ['dash_role'], [member_id])

    resources = await user_service.get_user_resources(
        user_id=member_id, scope=ResourceScope.DASHBOARD
    )
    assert [r.key for r in resources] == ['sales']


@pytest.mark.asyncio
async def test_empty_group_grants_nothing(
    test_session,
    setup_containers,
):
    """Membership alone is not access -- a role-less group contributes no roles."""
    _, _, user_container = setup_containers
    user_service = user_container.user_service()

    await create_role_with_resource(
        test_session,
        'direct_role',
        'Direct Role',
        scope=ResourceScope.DASHBOARD,
        resource_key='direct',
        resource_value='dashboard',
    )
    member_id = await create_user(test_session, 'member@example.com')
    async with test_session() as session:
        session.add(UserRole(user_id=member_id, role_id='direct_role'))
        await session.commit()
    await create_group(test_session, 'Role-less', None, [member_id])

    resources = await user_service.get_user_resources(
        user_id=member_id, scope=ResourceScope.DASHBOARD
    )
    assert [r.key for r in resources] == ['direct']


@pytest.mark.asyncio
async def test_effective_resources_union_direct_and_group(
    test_session,
    setup_containers,
):
    _, _, user_container = setup_containers
    user_service = user_container.user_service()

    await create_role_with_resource(
        test_session,
        'direct_role',
        'Direct Role',
        scope=ResourceScope.DATA,
        resource_key='region',
        resource_value='north',
    )
    await create_role_with_resource(
        test_session,
        'group_role',
        'Group Role',
        scope=ResourceScope.DATA,
        resource_key='region',
        resource_value='south',
    )
    member_id = await create_user(test_session, 'member@example.com')
    async with test_session() as session:
        session.add(UserRole(user_id=member_id, role_id='direct_role'))
        await session.commit()
    await create_group(test_session, 'South Team', ['group_role'], [member_id])

    resources = await user_service.get_user_resources(
        user_id=member_id, scope=ResourceScope.DATA
    )
    assert sorted(r.value for r in resources) == ['north', 'south']


@pytest.mark.asyncio
async def test_console_role_from_group_allows_login(
    test_session,
    setup_containers,
):
    """get_user_role_for_scope backs login; console access via a group must
    resolve, otherwise a group-only user could never sign in."""
    _, _, user_container = setup_containers
    user_service = user_container.user_service()

    await create_role_with_resource(test_session, 'console_role', 'Console Role')
    member_id = await create_user(test_session, 'grouponly@example.com')
    await create_group(test_session, 'Console Group', ['console_role'], [member_id])

    role_id = await user_service.get_user_role_for_scope(
        user_id=member_id, scope=ResourceScope.CONSOLE
    )
    assert role_id == 'console_role'


@pytest.mark.asyncio
async def test_admin_role_via_group_is_resolved(
    test_session,
    setup_containers,
):
    _, _, user_container = setup_containers
    user_service = user_container.user_service()

    await create_role_with_resource(test_session, 'admin_role', 'admin')
    member_id = await create_user(test_session, 'groupadmin@example.com')
    await create_group(test_session, 'Admins', ['admin_role'], [member_id])

    role_id = await user_service.get_user_role_for_scope(
        user_id=member_id, scope=ResourceScope.CONSOLE
    )
    assert role_id == 'admin_role'


@pytest.mark.asyncio
async def test_admin_count_includes_group_granted_admins(
    test_session,
    setup_containers,
):
    """The last-admin guard must see admins who hold the role via a group."""
    _, _, user_container = setup_containers
    user_service = user_container.user_service()

    await create_role_with_resource(test_session, 'admin_role', 'admin')
    direct_admin = await create_user(test_session, 'direct@example.com')
    group_admin = await create_user(test_session, 'viagroup@example.com')

    async with test_session() as session:
        session.add(UserRole(user_id=direct_admin, role_id='admin_role'))
        await session.commit()
    await create_group(test_session, 'Admins', ['admin_role'], [group_admin])

    admin_ids = await user_service.user_ids_with_role('admin_role')
    assert admin_ids == {direct_admin, group_admin}


@pytest.mark.asyncio
async def test_deleted_user_loses_group_membership(
    test_session,
    setup_containers,
):
    """delete_user soft-deletes, so membership rows are cleared explicitly."""
    _, _, user_container = setup_containers
    user_service = user_container.user_service()

    await create_role_with_resource(test_session, 'console_role', 'Console Role')
    member_id = await create_user(test_session, 'doomed@example.com')
    group_id = await create_group(
        test_session, 'Some Group', ['console_role'], [member_id]
    )

    assert await user_service.delete_user(member_id) is True

    async with test_session() as session:
        memberships = (
            await session.scalars(
                select(UserGroupMember).where(UserGroupMember.group_id == group_id)
            )
        ).all()
    assert memberships == []


# --------------------------------------------------------------------------
# Interaction with user creation and the directory listing
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_user_with_no_roles_but_group_granting_console(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_auth_admin_user_functions,
):
    await create_session(test_session, test_user_id, test_session_id)
    await create_role_with_resource(test_session, 'console_role', 'Console Role')
    group_id = await create_group(test_session, 'Console Group', ['console_role'])

    response = test_client.post(
        '/floware/v1/users',
        json={
            'email': 'grouponly@example.com',
            'password': 'Password123!',
            'first_name': 'Group',
            'last_name': 'Only',
            'group_ids': [group_id],
        },
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 200

    new_user_id = response.json()['data']['user_id']
    async with test_session() as session:
        direct_roles = (
            await session.scalars(
                select(UserRole).where(UserRole.user_id == new_user_id)
            )
        ).all()
        memberships = (
            await session.scalars(
                select(UserGroupMember.group_id).where(
                    UserGroupMember.user_id == new_user_id
                )
            )
        ).all()
    assert direct_roles == []
    assert [str(g) for g in memberships] == [group_id]


@pytest.mark.asyncio
async def test_create_user_rejects_duplicate_group_ids(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_auth_admin_user_functions,
):
    """Caught as input, not as a primary key violation on the membership row."""
    await create_session(test_session, test_user_id, test_session_id)
    await create_role_with_resource(test_session, 'console_role', 'Console Role')
    group_id = await create_group(test_session, 'Console Group', ['console_role'])

    response = test_client.post(
        '/floware/v1/users',
        json={
            'email': 'dupe@example.com',
            'password': 'Password123!',
            'first_name': 'Dupe',
            'last_name': 'Groups',
            'group_ids': [group_id, group_id],
        },
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 422
    assert 'unique' in str(response.json()).lower()


@pytest.mark.asyncio
async def test_create_user_rejects_duplicate_role_ids(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_auth_admin_user_functions,
):
    """Same primary key reasoning as duplicate group ids, on user_role."""
    await create_session(test_session, test_user_id, test_session_id)
    await create_role_with_resource(test_session, 'console_role', 'Console Role')

    response = test_client.post(
        '/floware/v1/users',
        json={
            'email': 'dupe-role@example.com',
            'password': 'Password123!',
            'first_name': 'Dupe',
            'last_name': 'Roles',
            'role_id': ['console_role', 'console_role'],
        },
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 422
    assert 'unique' in str(response.json()).lower()


@pytest.mark.asyncio
async def test_create_user_rejected_when_only_group_is_role_less(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_auth_admin_user_functions,
):
    """An empty group cannot satisfy the console requirement -- the user would
    be created unable to log in."""
    await create_session(test_session, test_user_id, test_session_id)
    group_id = await create_group(test_session, 'Role-less Group')

    response = test_client.post(
        '/floware/v1/users',
        json={
            'email': 'nologin@example.com',
            'password': 'Password123!',
            'first_name': 'No',
            'last_name': 'Login',
            'group_ids': [group_id],
        },
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 400
    assert 'console resource' in str(response.json())


@pytest.mark.asyncio
async def test_update_sole_admin_can_add_non_admin_role(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_auth_admin_user_functions,
):
    """Adding a non-admin role does not demote the sole admin, so it must pass.

    The session mock carries role_id='test_role_id', and the last-admin guard
    counts holders of that id (matching production, where an admin's JWT carries
    the admin role's id). The sole admin therefore holds 'test_role_id'.
    """
    await create_session(test_session, test_user_id, test_session_id)
    await create_role_with_resource(test_session, 'test_role_id', 'admin')
    await create_role_with_resource(
        test_session,
        'viewer_role',
        'Viewer',
        scope=ResourceScope.DASHBOARD,
        resource_key='viewer',
        resource_value='dashboard',
    )
    admin_id = await create_user(test_session, 'soleadmin@example.com')
    async with test_session() as session:
        session.add(UserRole(user_id=admin_id, role_id='test_role_id'))
        await session.commit()

    response = test_client.patch(
        '/floware/v1/users',
        json={'user_id': admin_id, 'add_role_ids': ['viewer_role']},
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 200

    async with test_session() as session:
        roles = (
            await session.scalars(
                select(UserRole.role_id).where(UserRole.user_id == admin_id)
            )
        ).all()
    assert sorted(str(r) for r in roles) == ['test_role_id', 'viewer_role']


@pytest.mark.asyncio
async def test_update_sole_admin_cannot_remove_admin_role(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_auth_admin_user_functions,
):
    await create_session(test_session, test_user_id, test_session_id)
    await create_role_with_resource(test_session, 'test_role_id', 'admin')
    admin_id = await create_user(test_session, 'soleadmin@example.com')
    async with test_session() as session:
        session.add(UserRole(user_id=admin_id, role_id='test_role_id'))
        await session.commit()

    response = test_client.patch(
        '/floware/v1/users',
        json={'user_id': admin_id, 'delete_role_ids': ['test_role_id']},
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 400
    assert 'admin' in str(response.json()).lower()

    async with test_session() as session:
        roles = (
            await session.scalars(
                select(UserRole.role_id).where(UserRole.user_id == admin_id)
            )
        ).all()
    assert [str(r) for r in roles] == ['test_role_id']


@pytest.mark.asyncio
async def test_update_sole_admin_cannot_leave_admin_group(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_auth_admin_user_functions,
):
    """Removing the sole admin from the group that grants admin must fail."""
    await create_session(test_session, test_user_id, test_session_id)
    await create_role_with_resource(test_session, 'test_role_id', 'admin')
    admin_id = await create_user(test_session, 'groupadmin@example.com')
    group_id = await create_group(test_session, 'Admins', ['test_role_id'], [admin_id])

    response = test_client.patch(
        '/floware/v1/users',
        json={'user_id': admin_id, 'delete_group_ids': [group_id]},
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 400
    assert 'admin' in str(response.json()).lower()

    async with test_session() as session:
        memberships = (
            await session.scalars(
                select(UserGroupMember.group_id).where(
                    UserGroupMember.user_id == admin_id
                )
            )
        ).all()
    assert [str(g) for g in memberships] == [group_id]


@pytest.mark.asyncio
async def test_update_user_adds_and_removes_groups(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_auth_admin_user_functions,
):
    await create_session(test_session, test_user_id, test_session_id)
    member_id = await create_user(test_session, 'movable@example.com')
    group_id = await create_group(test_session, 'Target Group')

    response = test_client.patch(
        '/floware/v1/users',
        json={'user_id': member_id, 'add_group_ids': [group_id]},
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 200

    async with test_session() as session:
        memberships = (
            await session.scalars(
                select(UserGroupMember.group_id).where(
                    UserGroupMember.user_id == member_id
                )
            )
        ).all()
    assert [str(g) for g in memberships] == [group_id]

    response = test_client.patch(
        '/floware/v1/users',
        json={'user_id': member_id, 'delete_group_ids': [group_id]},
        headers=auth_headers(auth_token),
    )
    assert response.status_code == 200

    async with test_session() as session:
        memberships = (
            await session.scalars(
                select(UserGroupMember).where(UserGroupMember.user_id == member_id)
            )
        ).all()
    assert memberships == []


@pytest.mark.asyncio
async def test_user_listing_includes_role_less_users_and_groups(
    test_client,
    test_session,
    test_user_id,
    test_session_id,
    auth_token,
    mock_auth_admin_user_functions,
):
    """A user with no direct roles must still appear. The previous inner join on
    user_role would have dropped them from the directory entirely."""
    await create_session(test_session, test_user_id, test_session_id)
    await create_role_with_resource(test_session, 'role_a', 'Role A')

    with_role = await create_user(test_session, 'hasrole@example.com')
    async with test_session() as session:
        session.add(UserRole(user_id=with_role, role_id='role_a'))
        await session.commit()

    group_only = await create_user(test_session, 'grouponly@example.com')
    await create_group(test_session, 'Engineering', ['role_a'], [group_only])

    response = test_client.get(
        '/floware/v1/users?force_fetch=1', headers=auth_headers(auth_token)
    )
    assert response.status_code == 200

    users = {u['email']: u for u in response.json()['data']['users']}
    assert 'grouponly@example.com' in users
    assert 'hasrole@example.com' in users

    # roles stays direct-only; the group is reported separately.
    assert users['grouponly@example.com']['roles'] == []
    assert [g['name'] for g in users['grouponly@example.com']['groups']] == [
        'Engineering'
    ]
    assert [r['name'] for r in users['hasrole@example.com']['roles']] == ['Role A']
    assert users['hasrole@example.com']['groups'] == []
