"""Admin endpoints for user groups.

A group bundles roles so they can be handed to several users at once. Members
hold the group's roles in addition to any directly assigned ones -- see
`UserService.effective_role_ids`, which is the single place that union is
defined.

Groups are allowed to be empty on both sides. A group with no roles grants
nothing and a group with no members is simply unused; neither is an error, so
every listing here uses outer joins and every payload lets the role list be
omitted. An inner join would hide exactly the group an admin just created and
still needs to configure.
"""

from typing import Optional
import uuid

from common_module.utils.validators import is_valid_uuid
from db_repo_module.models.role import Role
from db_repo_module.models.user import User
from db_repo_module.models.user_group import UserGroup
from db_repo_module.models.user_group_member import UserGroupMember
from db_repo_module.models.user_group_role import UserGroupRole
from dependency_injector.wiring import inject
from fastapi import APIRouter
from fastapi import Path
from fastapi import Query
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from sqlalchemy import and_
from sqlalchemy import delete
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from user_management_module.constants.cache import USER_DATA_PATTERN
from user_management_module.dependencies.injection import (
    CacheManagerDep,
    ResponseFormatterDep,
    UserGroupRepositoryDep,
)
from user_management_module.models.group import CreateGroupPayload
from user_management_module.models.group import GroupMembersPayload
from user_management_module.models.group import UpdateGroupPayload
from user_management_module.utils.user_utils import check_is_admin
from user_management_module.utils.user_utils import get_current_user

group_router = APIRouter(prefix='/v1/groups')


async def _require_admin(
    request: Request, response_formatter
) -> Optional[JSONResponse]:
    """Shared admin gate, matching the prologue used across access_controller."""
    role_id, _, _ = get_current_user(request)
    if not await check_is_admin(role_id):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )
    return None


def _invalid_group_id_response(group_id: str, response_formatter) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=response_formatter.buildErrorResponse(f'Invalid group id: {group_id}'),
    )


async def _validate_role_ids(session, role_ids: list[str]) -> Optional[str]:
    """Returns an error message when any role id does not exist."""
    if not role_ids:
        return None
    found = (await session.scalars(select(Role.id).where(Role.id.in_(role_ids)))).all()
    missing = set(role_ids) - {str(role_id) for role_id in found}
    if missing:
        return f'Invalid role IDs: {", ".join(sorted(missing))}'
    return None


async def _validate_user_ids(session, user_ids: list[str]) -> Optional[str]:
    """Returns an error message when any user id is unknown or deleted."""
    if not user_ids:
        return None
    malformed = [user_id for user_id in user_ids if not is_valid_uuid(user_id)]
    if malformed:
        return f'Invalid user IDs: {", ".join(sorted(malformed))}'

    found = (
        await session.scalars(
            select(User.id).where(and_(User.id.in_(user_ids), User.deleted.is_(False)))
        )
    ).all()
    missing = set(user_ids) - {str(user_id) for user_id in found}
    if missing:
        return f'Invalid user IDs: {", ".join(sorted(missing))}'
    return None


@group_router.post('')
@inject
async def create_group(
    request: Request,
    payload: CreateGroupPayload,
    response_formatter: ResponseFormatterDep,
    group_repository: UserGroupRepositoryDep,
    cache_manager: CacheManagerDep,
):
    denied = await _require_admin(request, response_formatter)
    if denied:
        return denied

    existing = await group_repository.find_one(name=payload.name)
    if existing:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f"A group with the name '{payload.name}' already exists"
            ),
        )

    async with group_repository.session() as session:
        role_error = await _validate_role_ids(session, payload.role_ids)
        if role_error:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(role_error),
            )

        user_error = await _validate_user_ids(session, payload.user_ids)
        if user_error:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(user_error),
            )

        group = UserGroup(
            id=uuid.uuid4(),
            name=payload.name,
            description=payload.description,
        )
        session.add(group)
        await session.flush()
        # Read the id before commit: commit expires the instance, and touching
        # an expired attribute afterwards would trigger a lazy refresh outside
        # the async context.
        group_id = str(group.id)

        # Both lists may be empty; an empty group is a valid starting state.
        session.add_all(
            [
                UserGroupRole(group_id=group_id, role_id=role_id)
                for role_id in payload.role_ids
            ]
        )
        session.add_all(
            [
                UserGroupMember(group_id=group_id, user_id=user_id)
                for user_id in payload.user_ids
            ]
        )
        await session.commit()

    cache_manager.invalidate_query(USER_DATA_PATTERN)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            data={'message': 'Created group successfully', 'group_id': group_id}
        ),
    )


@group_router.get('')
@inject
async def list_groups(
    request: Request,
    response_formatter: ResponseFormatterDep,
    group_repository: UserGroupRepositoryDep,
    search: Optional[str] = Query(None, description='Search by name or description'),
    limit: Optional[int] = Query(
        None, description='Maximum number of groups to return (all when omitted)'
    ),
    offset: int = Query(0, description='Number of groups to skip'),
):
    denied = await _require_admin(request, response_formatter)
    if denied:
        return denied

    filters = []
    if search and search.strip():
        term = f'%{search.strip()}%'
        filters.append(
            or_(UserGroup.name.ilike(term), UserGroup.description.ilike(term))
        )

    # Counts come from correlated subqueries so a group with no roles or no
    # members still appears, with a zero count rather than being joined away.
    role_count = (
        select(func.count())
        .select_from(UserGroupRole)
        .where(UserGroupRole.group_id == UserGroup.id)
        .scalar_subquery()
    )
    member_count = (
        select(func.count())
        .select_from(UserGroupMember)
        .where(UserGroupMember.group_id == UserGroup.id)
        .scalar_subquery()
    )

    async with group_repository.session() as session:
        total = (
            await session.execute(
                select(func.count()).select_from(UserGroup).where(*filters)
            )
        ).scalar() or 0

        statement = (
            select(UserGroup, role_count.label('rc'), member_count.label('mc'))
            .where(*filters)
            .order_by(UserGroup.name)
            .offset(offset)
        )
        if limit is not None:
            statement = statement.limit(limit)

        rows = (await session.execute(statement)).all()

    groups = []
    for group, group_role_count, group_member_count in rows:
        entry = group.to_dict()
        entry['role_count'] = group_role_count
        entry['member_count'] = group_member_count
        groups.append(entry)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            data={'groups': groups, 'total': total}
        ),
    )


@group_router.get('/{group_id}')
@inject
async def get_group(
    request: Request,
    response_formatter: ResponseFormatterDep,
    group_repository: UserGroupRepositoryDep,
    group_id: str = Path(..., description='Group id to fetch'),
):
    denied = await _require_admin(request, response_formatter)
    if denied:
        return denied

    if not is_valid_uuid(group_id):
        return _invalid_group_id_response(group_id, response_formatter)

    async with group_repository.session() as session:
        group = (
            await session.scalars(
                select(UserGroup)
                .where(UserGroup.id == group_id)
                .options(selectinload(UserGroup.roles))
            )
        ).first()

        if not group:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=response_formatter.buildErrorResponse(
                    'Group not found with the given ID.'
                ),
            )

        members = (
            (
                await session.execute(
                    select(User)
                    .join(UserGroupMember, UserGroupMember.user_id == User.id)
                    .where(
                        and_(
                            UserGroupMember.group_id == group_id,
                            User.deleted.is_(False),
                        )
                    )
                )
            )
            .scalars()
            .all()
        )

        # An empty group reports empty lists rather than 404 -- it exists, it
        # simply has nothing in it yet.
        data = group.to_dict()
        data['roles'] = [role.to_dict() for role in group.roles]
        data['users'] = [member.to_dict() for member in members]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(data={'group': data}),
    )


@group_router.patch('/{group_id}')
@inject
async def update_group(
    request: Request,
    payload: UpdateGroupPayload,
    response_formatter: ResponseFormatterDep,
    group_repository: UserGroupRepositoryDep,
    cache_manager: CacheManagerDep,
    group_id: str = Path(..., description='Group id to update'),
):
    denied = await _require_admin(request, response_formatter)
    if denied:
        return denied

    if not is_valid_uuid(group_id):
        return _invalid_group_id_response(group_id, response_formatter)

    group = await group_repository.find_one(id=group_id)
    if not group:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                'Group not found with the given ID.'
            ),
        )

    if (
        payload.name is None
        and payload.description is None
        and payload.role_ids is None
    ):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'No fields provided for update'
            ),
        )

    if payload.name is not None and payload.name != group.name:
        existing = await group_repository.find_one(name=payload.name)
        if existing:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    f"A group with the name '{payload.name}' already exists"
                ),
            )

    async with group_repository.session() as session:
        role_error = await _validate_role_ids(session, payload.role_ids or [])
        if role_error:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(role_error),
            )

        # None means "leave roles alone"; [] means "remove every role". Treating
        # the empty list as a no-op would make emptying a group impossible.
        if payload.role_ids is not None:
            await session.execute(
                delete(UserGroupRole.__table__).where(
                    UserGroupRole.group_id == group_id
                )
            )
            session.add_all(
                [
                    UserGroupRole(group_id=group_id, role_id=role_id)
                    for role_id in payload.role_ids
                ]
            )

        group_in_session = await session.get(UserGroup, group_id)
        if payload.name is not None:
            group_in_session.name = payload.name
        if payload.description is not None:
            group_in_session.description = payload.description

        await session.commit()

    cache_manager.invalidate_query(USER_DATA_PATTERN)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            data={'message': 'Group updated successfully'}
        ),
    )


@group_router.delete('/{group_id}')
@inject
async def delete_group(
    request: Request,
    response_formatter: ResponseFormatterDep,
    group_repository: UserGroupRepositoryDep,
    cache_manager: CacheManagerDep,
    group_id: str = Path(..., description='Group id to delete'),
):
    denied = await _require_admin(request, response_formatter)
    if denied:
        return denied

    if not is_valid_uuid(group_id):
        return _invalid_group_id_response(group_id, response_formatter)

    group = await group_repository.find_one(id=group_id)
    if not group:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                'Group not found with the given ID.'
            ),
        )

    # Both join tables cascade. Members keep their directly assigned roles and
    # lose only what this group was granting them.
    await group_repository.delete_all(id=group_id)

    cache_manager.invalidate_query(USER_DATA_PATTERN)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            data={'message': 'Group deleted successfully'}
        ),
    )


@group_router.post('/{group_id}/members')
@inject
async def add_group_members(
    request: Request,
    payload: GroupMembersPayload,
    response_formatter: ResponseFormatterDep,
    group_repository: UserGroupRepositoryDep,
    cache_manager: CacheManagerDep,
    group_id: str = Path(..., description='Group id to add members to'),
):
    denied = await _require_admin(request, response_formatter)
    if denied:
        return denied

    if not is_valid_uuid(group_id):
        return _invalid_group_id_response(group_id, response_formatter)

    group = await group_repository.find_one(id=group_id)
    if not group:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                'Group not found with the given ID.'
            ),
        )

    async with group_repository.session() as session:
        user_error = await _validate_user_ids(session, payload.user_ids)
        if user_error:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(user_error),
            )

        existing_members = (
            await session.scalars(
                select(UserGroupMember.user_id).where(
                    and_(
                        UserGroupMember.group_id == group_id,
                        UserGroupMember.user_id.in_(payload.user_ids),
                    )
                )
            )
        ).all()
        already_member = {str(user_id) for user_id in existing_members}

        session.add_all(
            [
                UserGroupMember(group_id=group_id, user_id=user_id)
                for user_id in payload.user_ids
                if user_id not in already_member
            ]
        )
        await session.commit()

    cache_manager.invalidate_query(USER_DATA_PATTERN)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            data={'message': 'Group members added successfully'}
        ),
    )


@group_router.delete('/{group_id}/members')
@inject
async def remove_group_members(
    request: Request,
    payload: GroupMembersPayload,
    response_formatter: ResponseFormatterDep,
    group_repository: UserGroupRepositoryDep,
    cache_manager: CacheManagerDep,
    group_id: str = Path(..., description='Group id to remove members from'),
):
    denied = await _require_admin(request, response_formatter)
    if denied:
        return denied

    if not is_valid_uuid(group_id):
        return _invalid_group_id_response(group_id, response_formatter)

    group = await group_repository.find_one(id=group_id)
    if not group:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                'Group not found with the given ID.'
            ),
        )

    async with group_repository.session() as session:
        await session.execute(
            delete(UserGroupMember.__table__).where(
                and_(
                    UserGroupMember.group_id == group_id,
                    UserGroupMember.user_id.in_(payload.user_ids),
                )
            )
        )
        await session.commit()

    cache_manager.invalidate_query(USER_DATA_PATTERN)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            data={'message': 'Group members removed successfully'}
        ),
    )
