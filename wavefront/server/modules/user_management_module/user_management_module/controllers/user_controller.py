import secrets
from typing import List, Optional
from urllib.parse import quote

from common_module.feature.feature_flag import (
    ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG,
    is_feature_enabled,
)
from common_module.log.logger import logger
from db_repo_module.models.resource import Resource
from db_repo_module.models.resource import ResourceScope
from db_repo_module.models.role import Role
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.models.user import User
from db_repo_module.models.user_group import UserGroup
from db_repo_module.models.user_group_member import UserGroupMember
from db_repo_module.models.user_role import UserRole
from dependency_injector.wiring import inject
from fastapi import BackgroundTasks, Path, Query
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy import and_
from sqlalchemy import cast
from sqlalchemy import delete
from sqlalchemy import exists
from sqlalchemy import literal
from sqlalchemy import select
from sqlalchemy import or_
from sqlalchemy import func
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import ARRAY, JSON

from user_management_module.dependencies.injection import (
    AccountLockoutServiceDep,
    CacheManagerDep,
    CommonCacheDep,
    EmailSenderDep,
    RecaptchaServiceDep,
    ResponseFormatterDep,
    TokenServiceDep,
    UserConfigDep,
    UserRepositoryDep,
    UserRoleRepositoryDep,
    UserServiceDep,
)
from user_management_module.constants.auth import PASSWORD_RESET_TOKEN_PURPOSE
from user_management_module.constants.cache import (
    USER_DATA_PATTERN,
    password_reset_latest_key,
    user_by_id_cache_key,
    user_list_cache_key,
)
from user_management_module.models.user_schema import (
    NewUser,
    ResetUser,
    SendResetPasswordEmailRequest,
    UpdateUser,
)
from user_management_module.utils.email_templates import (
    PASSWORD_RESET_SUBJECT,
    build_password_reset_email,
)
from user_management_module.utils.password_utils import hash_password
from user_management_module.utils.rate_limit import (
    DEFAULT_COOLDOWN_SECONDS,
    password_reset_rate_limited,
)
from user_management_module.utils.user_utils import (
    can_read_users,
    check_is_admin,
    normalize_email,
)
from user_management_module.utils.user_utils import get_current_user
from user_management_module.services.recaptcha_service import (
    RECAPTCHA_ACTION_RESET_PASSWORD,
    RECAPTCHA_ACTION_SEND_RESET_PASSWORD,
)
import json
from common_module.utils.serializer import serialize_values
from common_module.utils.validators import is_valid_uuid

user_router = APIRouter(prefix='/v1')

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='token')

# The reset-password-email endpoint is unauthenticated, so every outcome it can
# reach has to look identical from the outside. Anything that varies with the
# submitted address -- a distinct error, a different status code -- lets an
# attacker enumerate registered accounts by feeding it a wordlist. Real reasons
# for not sending (unknown address, deleted user, locked account, mail failure)
# are logged instead of returned.
PASSWORD_RESET_GENERIC_MESSAGE = (
    'If an account exists for this email address, '
    'a password reset link has been sent to it.'
)


def _password_reset_generic_response(response_formatter) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': PASSWORD_RESET_GENERIC_MESSAGE}
        ),
    )


PASSWORD_RESET_INVALID_MESSAGE = (
    "Sorry, we couldn't verify your identity, or your password reset link "
    'has expired. Please try again or request a new reset link.'
)


def _password_reset_invalid_response(response_formatter) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=response_formatter.buildErrorResponse(PASSWORD_RESET_INVALID_MESSAGE),
    )


async def _deliver_password_reset_email(
    email_sender, recipients: str, reset_url: str
) -> None:
    try:
        email_response = await email_sender.send(
            subject=PASSWORD_RESET_SUBJECT,
            body_html=build_password_reset_email(reset_url),
            recipients=recipients,
        )
        if not email_response:
            logger.error('Error while sending password reset email')
    except Exception as exc:
        logger.error(f'Error while sending password reset email: {exc}')


def _recaptcha_failure_response(
    response_formatter, error_message: Optional[str]
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content=response_formatter.buildErrorResponse(
            error_message or 'reCAPTCHA verification failed'
        ),
    )


@user_router.post('/users')
@inject
async def create_user(
    new_user: NewUser,
    request: Request,
    response_formatter: ResponseFormatterDep,
    user_repository: UserRepositoryDep,
    user_service: UserServiceDep,
    cache_manager: CacheManagerDep,
):
    role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)

    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )

    # Groups can carry the admin role too, so admin status is decided over the
    # direct roles and the group roles together.
    assignment_role_ids = await user_service.resolve_assignment_role_ids(
        role_ids=new_user.role_id, group_ids=new_user.group_ids
    )
    is_creating_admin = role_id in assignment_role_ids

    existing_user = await user_repository.find_one(email=new_user.email)
    if existing_user:
        if existing_user.deleted:
            return await user_service.reactivate_user(
                existing_user, new_user, role_id, response_formatter
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'User with the same email already exists'
                ),
            )

    if new_user.username:
        existing_by_username = await user_repository.find_one(
            username=new_user.username
        )
        if existing_by_username and not existing_by_username.deleted:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'User with the same username already exists'
                ),
            )

    async with user_repository.session() as session:
        try:
            # Console access may come from a group, but an empty group grants
            # nothing -- so a user with no direct roles whose only groups are
            # role-less still fails here, as they could not log in otherwise.
            if not is_creating_admin:
                get_console_resources_query = (
                    select(Resource)
                    .join(RoleResource, Resource.id == RoleResource.resource_id)
                    .where(
                        and_(
                            RoleResource.role_id.in_(assignment_role_ids),
                            Resource.scope == ResourceScope.CONSOLE,
                        )
                    )
                )
                result = await session.execute(get_console_resources_query)
                console_resources = result.scalars().all()
                if len(console_resources) == 0:
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content=response_formatter.buildErrorResponse(
                            'Atleast one console resource is mandatory'
                        ),
                    )

            hashed_password = hash_password(new_user.password)
            user = User(
                email=new_user.email,
                username=new_user.username,
                password=hashed_password,
                first_name=new_user.first_name,
                last_name=new_user.last_name,
            )

            # Check for valid roles
            query = select(Role).where(Role.id.in_(new_user.role_id))
            result = await session.execute(query)
            existing_roles = result.scalars().all()
            existing_role_ids = {str(role.id) for role in existing_roles}

            invalid_roles = set(new_user.role_id) - existing_role_ids
            if invalid_roles:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=response_formatter.buildErrorResponse(
                        f'Invalid role IDs: {", ".join(invalid_roles)}'
                    ),
                )

            if new_user.group_ids:
                group_query = select(UserGroup.id).where(
                    UserGroup.id.in_(new_user.group_ids)
                )
                group_result = await session.execute(group_query)
                existing_group_ids = {str(g_id) for g_id in group_result.scalars()}

                invalid_groups = set(new_user.group_ids) - existing_group_ids
                if invalid_groups:
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content=response_formatter.buildErrorResponse(
                            f'Invalid group IDs: {", ".join(sorted(invalid_groups))}'
                        ),
                    )

            # Create user
            session.add(user)
            await session.flush()
            user_id = user.id

            user_roles = [
                UserRole(user_id=user_id, role_id=r_id) for r_id in new_user.role_id
            ]
            session.add_all(user_roles)

            session.add_all(
                [
                    UserGroupMember(user_id=user_id, group_id=g_id)
                    for g_id in new_user.group_ids
                ]
            )

            await session.commit()

            cache_manager.invalidate_query(USER_DATA_PATTERN)

            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=response_formatter.buildSuccessResponse(
                    {
                        'message': 'Created user successfully',
                        'user_id': str(user_id),
                    }
                ),
            )

        except Exception as e:
            await session.rollback()
            logger.error(f'Error while creating user, {e}')
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=response_formatter.buildErrorResponse('Failed to create user'),
            )


@user_router.patch('/users')
@inject
async def update_user(
    update_user: UpdateUser,
    request: Request,
    response_formatter: ResponseFormatterDep,
    user_repository: UserRepositoryDep,
    user_role_repository: UserRoleRepositoryDep,
    cache_manager: CacheManagerDep,
    user_service: UserServiceDep,
):
    role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)

    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )

    target_user = await user_repository.find_one(id=update_user.user_id)
    if not target_user or target_user.deleted:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('User not found'),
        )

    add_role_ids = update_user.add_role_ids or []
    delete_role_ids = update_user.delete_role_ids or []
    add_group_ids = update_user.add_group_ids or []
    delete_group_ids = update_user.delete_group_ids or []

    # Build the set of profile fields to edit, enforcing uniqueness for the
    # columns that carry a DB unique constraint (email, username).
    profile_updates: dict = {}
    if update_user.email is not None and update_user.email != target_user.email:
        existing_by_email = await user_repository.find_one(email=update_user.email)
        if (
            existing_by_email
            and not existing_by_email.deleted
            and str(existing_by_email.id) != str(update_user.user_id)
        ):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'User with the same email already exists'
                ),
            )
        profile_updates['email'] = update_user.email

    if (
        update_user.username is not None
        and update_user.username != target_user.username
    ):
        existing_by_username = await user_repository.find_one(
            username=update_user.username
        )
        if (
            existing_by_username
            and not existing_by_username.deleted
            and str(existing_by_username.id) != str(update_user.user_id)
        ):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'User with the same username already exists'
                ),
            )
        profile_updates['username'] = update_user.username

    if update_user.password is not None:
        profile_updates['password'] = hash_password(update_user.password)
    if update_user.first_name is not None:
        profile_updates['first_name'] = update_user.first_name
    if update_user.last_name is not None:
        profile_updates['last_name'] = update_user.last_name

    async with user_role_repository.session() as session:
        if add_role_ids:
            # Check for valid roles
            query = select(Role).where(Role.id.in_(add_role_ids))
            result = await session.execute(query)
            existing_roles = result.scalars().all()
            existing_role_ids = {str(role.id) for role in existing_roles}

            invalid_roles = set(add_role_ids) - existing_role_ids
            if invalid_roles:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=response_formatter.buildErrorResponse(
                        f'Invalid role IDs: {", ".join(invalid_roles)}'
                    ),
                )

        if add_group_ids:
            group_query = select(UserGroup.id).where(UserGroup.id.in_(add_group_ids))
            group_result = await session.execute(group_query)
            existing_group_ids = {str(g_id) for g_id in group_result.scalars()}

            invalid_groups = set(add_group_ids) - existing_group_ids
            if invalid_groups:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=response_formatter.buildErrorResponse(
                        f'Invalid group IDs: {", ".join(sorted(invalid_groups))}'
                    ),
                )

        # Guard against demoting the only remaining admin. Apply the mutation
        # first, then re-count: that lets a sole admin still pick up additional
        # non-admin roles or groups, while still rejecting a change that would
        # leave the instance with none. The lock keeps a concurrent request
        # from slipping between the two counts.
        mutating_roles_or_groups = bool(
            add_role_ids or delete_role_ids or add_group_ids or delete_group_ids
        )
        admins_before: set[str] = set()
        if mutating_roles_or_groups:
            await user_service.lock_role(session, role_id)
            admins_before = await user_service.user_ids_with_role(
                role_id, session=session
            )

        if add_role_ids:
            existing_links = await user_role_repository.find(
                user_id=update_user.user_id, role_id=add_role_ids, session=session
            )
            already_assigned = {str(link.role_id) for link in existing_links}
            new_user_roles = [
                UserRole(user_id=update_user.user_id, role_id=r_id)
                for r_id in add_role_ids
                if r_id not in already_assigned
            ]
            session.add_all(new_user_roles)

        if delete_role_ids:
            query = delete(UserRole.__table__).where(
                and_(
                    UserRole.user_id == update_user.user_id,
                    UserRole.role_id.in_(delete_role_ids),
                )
            )
            await session.execute(query)

        if add_group_ids:
            existing_memberships = await session.scalars(
                select(UserGroupMember.group_id).where(
                    and_(
                        UserGroupMember.user_id == update_user.user_id,
                        UserGroupMember.group_id.in_(add_group_ids),
                    )
                )
            )
            already_member = {str(g_id) for g_id in existing_memberships}
            session.add_all(
                [
                    UserGroupMember(user_id=update_user.user_id, group_id=g_id)
                    for g_id in add_group_ids
                    if g_id not in already_member
                ]
            )

        if delete_group_ids:
            query = delete(UserGroupMember.__table__).where(
                and_(
                    UserGroupMember.user_id == update_user.user_id,
                    UserGroupMember.group_id.in_(delete_group_ids),
                )
            )
            await session.execute(query)

        if mutating_roles_or_groups and admins_before:
            await session.flush()
            admins_after = await user_service.user_ids_with_role(
                role_id, session=session
            )
            if not admins_after:
                await session.rollback()
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=response_formatter.buildErrorResponse(
                        error='Atleast one admin is mandatory, please assign another user as admin before updating this user.'
                    ),
                )

        if profile_updates:
            user_in_session = await session.get(User, update_user.user_id)
            for field, value in profile_updates.items():
                setattr(user_in_session, field, value)

        await session.commit()

    # Invalidate all user_data cache entries
    cache_manager.invalidate_query(USER_DATA_PATTERN)
    cache_manager.remove(str(update_user.user_id))
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Updated successfully'}
        ),
    )


@user_router.get('/users')
@inject
async def get_all_user(
    request: Request,
    response_formatter: ResponseFormatterDep,
    user_repository: UserRepositoryDep,
    cache_manager: CacheManagerDep,
    search: Optional[str] = Query(
        None, max_length=200, description='Search by name or email'
    ),
    roles: Optional[List[str]] = Query(None, description='Filter by role name'),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    force_fetch: int = Query(0, ge=0, le=1),
):
    """List users.

    Admins get the full directory entry: roles, groups and username alongside
    the name and email. With ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG set, everyone
    else gets a name-and-email lookup — id, email, first_name, last_name and
    nothing more — which is what the console needs to put a name to an id it
    already holds. Without the flag, non-admins are refused outright.
    """
    # This is can_read_users' gate, inlined: the admin bit decides the payload
    # shape here, not just access, and calling both would re-resolve the role.
    role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)

    if not is_admin and not is_feature_enabled(ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )

    # Refused rather than ignored: `?roles=admin` would partition the directory
    # by role and hand back exactly the membership the trimmed payload withholds,
    # and silently dropping the filter would answer a question that was not asked.
    if not is_admin and roles:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Filtering users by role requires admin access'
            ),
        )

    # checking the cache for the keys
    cache_key = user_list_cache_key(
        offset, limit, search, roles, include_roles=is_admin
    )
    if not force_fetch:
        cached_result = cache_manager.get_str(cache_key)
        if cached_result:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=response_formatter.buildSuccessResponse(
                    {'users': json.loads(cached_result)},
                ),
            )
    async with user_repository.session() as session:
        if not is_admin:
            # The trimmed directory: no roles, no groups, and no username. The
            # columns are left out of the query rather than stripped from the
            # result, so there is no shape for a later edit to forget to filter.
            query = select(
                User.id,
                User.first_name,
                User.last_name,
                User.email,
            ).where(User.deleted.is_(False))
        else:
            query = _admin_user_listing_query(roles)

        # Add search conditions
        if search and search.strip():
            # for first name and last name search
            name = search.split(' ')
            filters = []
            if name[0]:
                filters.append(User.first_name.ilike(f'%{name[0]}%'))
            if len(name) > 1 and name[1]:
                filters.append(User.last_name.ilike(f'%{name[1]}%'))
            filters.append(User.email.ilike(f'%{search}%'))
            # Username is not in the non-admin payload, so matching on it there
            # would return rows with no visible reason for having matched.
            if is_admin:
                filters.append(User.username.ilike(f'%{search}%'))
            query = query.where(or_(*filters))

        # Add role filter. An EXISTS keeps this a row filter, so users are
        # selected on their direct roles just as before. Admin-only: the guard
        # above rejects the parameter for everyone else.
        if roles:
            query = query.where(
                exists(
                    select(literal(1))
                    .select_from(UserRole)
                    .join(Role, Role.id == UserRole.role_id)
                    .where(UserRole.user_id == User.id, Role.name.in_(roles))
                )
            )

        # Without GROUP BY there is no incidental ordering left to lean on, and
        # offset/limit paging needs a stable one.
        query = query.order_by(User.id).offset(offset).limit(limit)

        # Execute query
        result = await session.execute(query)
        rows = result.all()

    # Cache and return result
    serialize_result = serialize_values(rows)
    cache_manager.add(cache_key, json.dumps(serialize_result), expiry=60 * 60)  # 1 hour
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'users': serialize_result}),
    )


def _admin_user_listing_query(roles: Optional[List[str]]):
    """The full directory row: name, email, username, roles and groups."""
    empty_json_array = cast(postgresql.array([], type_=postgresql.JSON), ARRAY(JSON))

    # Roles and groups are aggregated in correlated subqueries rather than by
    # joining and grouping. Two reasons: joining both would multiply each
    # user's roles by their groups, and de-duplicating that fan-out would need
    # array_agg(DISTINCT ...), which Postgres rejects on json values for want
    # of an equality operator.
    #
    # Aggregating over no rows yields NULL, so each coalesces to an empty
    # array. That is what lets a user with no direct roles (drawing access
    # from a group instead) or no groups still appear in the directory.
    #
    # `roles` stays direct-only. Roles inherited from a group are deliberately
    # not merged in, so the field keeps the meaning it has always had.
    roles_aggregate = (
        select(
            func.coalesce(
                func.array_agg(
                    func.json_build_object('id', Role.id, 'name', Role.name)
                ),
                empty_json_array,
            )
        )
        .select_from(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == User.id)
    )

    # When filtering by role name the aggregate is filtered to match, so a
    # filtered listing keeps reporting only the roles that matched, exactly
    # as the previous join-and-group query did.
    if roles:
        roles_aggregate = roles_aggregate.where(Role.name.in_(roles))

    groups_aggregate = (
        select(
            func.coalesce(
                func.array_agg(
                    func.json_build_object('id', UserGroup.id, 'name', UserGroup.name)
                ),
                empty_json_array,
            )
        )
        .select_from(UserGroupMember)
        .join(UserGroup, UserGroup.id == UserGroupMember.group_id)
        .where(UserGroupMember.user_id == User.id)
    )

    return select(
        User.id,
        User.first_name,
        User.last_name,
        User.email,
        User.username,
        roles_aggregate.scalar_subquery().label('roles'),
        groups_aggregate.scalar_subquery().label('groups'),
    ).where(User.deleted.is_(False))


@user_router.get('/users/{user_id}')
@inject
async def get_user(
    request: Request,
    response_formatter: ResponseFormatterDep,
    user_repository: UserRepositoryDep,
    cache_manager: CacheManagerDep,
    user_id: str = Path(..., description='User id to fetch'),
    force_fetch: int = Query(0, ge=0, le=1),
):
    """Fetch one user by id — name and email, without roles.

    Admin only, like the listing endpoint it complements, unless
    ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG opens both up. It resolves an id the
    caller already holds (a quotation's assignee, say) rather than returning a
    page, so the console does not have to pull the whole directory to put a name
    to one id.

    Cached for an hour under a key from `constants.cache`, so the existing
    `invalidate_query(USER_DATA_PATTERN)` calls in create/update/delete already
    clear it — there is no new invalidation to remember. Pass `force_fetch=1` to
    read through to the database.
    """
    if not await can_read_users(request):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )

    # User.id is a uuid column, so a malformed id would otherwise reach the
    # database and come back as a 500 rather than a 400.
    if not is_valid_uuid(user_id):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'Invalid user id: {user_id}'
            ),
        )

    cache_key = user_by_id_cache_key(user_id)
    if not force_fetch:
        cached_result = cache_manager.get_str(cache_key)
        if cached_result:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=response_formatter.buildSuccessResponse(
                    {'user': json.loads(cached_result)}
                ),
            )

    user = await user_repository.find_one(id=user_id)
    if not user or user.deleted:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('User not found'),
        )

    serialize_result = user.to_dict()

    cache_manager.add(cache_key, json.dumps(serialize_result), expiry=60 * 60)  # 1 hour
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'user': serialize_result}),
    )


@user_router.get('/users/{user_id}/groups')
@inject
async def get_user_groups(
    request: Request,
    response_formatter: ResponseFormatterDep,
    user_repository: UserRepositoryDep,
    user_id: str = Path(..., description='User id whose groups to fetch'),
):
    """Groups one user belongs to.

    Returns an empty list for a user in no groups, which is a perfectly normal
    state -- group membership is optional.
    """
    role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)

    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )

    if not is_valid_uuid(user_id):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'Invalid user id: {user_id}'
            ),
        )

    user = await user_repository.find_one(id=user_id)
    if not user or user.deleted:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('User not found'),
        )

    async with user_repository.session() as session:
        groups = (
            (
                await session.execute(
                    select(UserGroup)
                    .join(
                        UserGroupMember,
                        UserGroupMember.group_id == UserGroup.id,
                    )
                    .where(UserGroupMember.user_id == user_id)
                    .order_by(UserGroup.name)
                )
            )
            .scalars()
            .all()
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'groups': [group.to_dict() for group in groups]}
        ),
    )


@user_router.delete('/users')
@inject
async def delete_user(
    request: Request,
    response_formatter: ResponseFormatterDep,
    user_repository: UserRepositoryDep,
    user_service: UserServiceDep,
    cache_manager: CacheManagerDep,
    delete_id: str = Query(alias='id', min_length=1, max_length=100),
):
    role_id, user_id, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)

    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )

    if not is_valid_uuid(delete_id):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'Invalid user id: {delete_id}'
            ),
        )

    # Counted across direct assignments and group membership alike, so the last
    # admin cannot be deleted even when their admin role comes from a group.
    #
    # The lock is held across both the count and the delete. delete_user commits
    # through its own transactions, but those commits land before this one
    # releases the lock, so the next request through here blocks until then and
    # always counts post-delete state.
    async with user_repository.session() as guard_session:
        await user_service.lock_role(guard_session, role_id)
        admin_user_ids = await user_service.user_ids_with_role(
            role_id, session=guard_session
        )
        if len(admin_user_ids) == 1 and user_id == delete_id:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'Atleast one admin is mandatory, please assign another user as admin before deleting this user.'
                ),
            )

        response = await user_service.delete_user(delete_id)
        await guard_session.commit()

    # Invalidate all user_data cache entries
    cache_manager.invalidate_query(USER_DATA_PATTERN)

    if response:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'message': 'User deleted successfully.'}
            ),
        )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=response_formatter.buildErrorResponse('Failed to delete the user.'),
    )


@user_router.post('/user/send-reset-password-email')
@inject
async def send_reset_url(
    payload: SendResetPasswordEmailRequest,
    background_tasks: BackgroundTasks,
    user_repository: UserRepositoryDep,
    user_reset_cache: CommonCacheDep,
    response_formatter: ResponseFormatterDep,
    token_service: TokenServiceDep,
    config: UserConfigDep,
    email_sender: EmailSenderDep,
    account_lockout_service: AccountLockoutServiceDep,
    recaptcha_service: RecaptchaServiceDep,
):
    is_recaptcha_valid, recaptcha_error = await recaptcha_service.verify(
        payload.recaptcha_token, action=RECAPTCHA_ACTION_SEND_RESET_PASSWORD
    )
    if not is_recaptcha_valid:
        return _recaptcha_failure_response(response_formatter, recaptcha_error)

    email = normalize_email(payload.email)
    try:
        # Rate-limit before the lookup so a 429 never depends on whether the
        # account exists. Per-address only; the load balancer covers IP/volume.
        if password_reset_rate_limited(user_reset_cache, config, email):
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content=response_formatter.buildErrorResponse(
                    PASSWORD_RESET_GENERIC_MESSAGE
                ),
                headers={'Retry-After': str(DEFAULT_COOLDOWN_SECONDS)},
            )

        # checking if the user exists in the db
        user_with_email = await user_repository.find_one(email=email)
        if not user_with_email or user_with_email.deleted:
            logger.info('Password reset requested for an unknown or deleted account')
            return _password_reset_generic_response(response_formatter)

        is_locked, _ = await account_lockout_service.check_account_lockout(
            user_with_email
        )
        if is_locked:
            # A locked account gets no reset link, but saying so would confirm the
            # address is registered, so the caller sees the same message as always.
            logger.info(
                f'Password reset skipped for locked account {user_with_email.id}'
            )
            return _password_reset_generic_response(response_formatter)

        # creating an jwt token for reseting the password
        random_digit = secrets.token_hex(16)

        decoded_url = token_service.create_token(
            payload={
                'code': random_digit,
                'purpose': PASSWORD_RESET_TOKEN_PURPOSE,
            },
            is_temporary=True,
        )

        # A new request supersedes any earlier unused link for this user.
        pointer_key = password_reset_latest_key(str(user_with_email.id))
        previous_code = user_reset_cache.pop_str(pointer_key)
        if previous_code:
            user_reset_cache.remove(previous_code)
        user_reset_cache.add(random_digit, str(user_with_email.id), expiry=600)
        user_reset_cache.add(pointer_key, random_digit, expiry=600)

        # generating the url
        forget_url_link = (
            f'{config["web"]["url"]}/reset-password?token={quote(decoded_url, safe="")}'
        )

        # Sent from the primary email connection, so changing the platform
        # sender is an admin action rather than a redeploy. The send runs after
        # the response so SMTP latency cannot distinguish a live address.
        background_tasks.add_task(
            _deliver_password_reset_email,
            email_sender,
            email,
            forget_url_link,
        )

        return _password_reset_generic_response(response_formatter)
    except Exception as exc:
        logger.error(f'Password reset request failed: {exc}', exc_info=True)
        return _password_reset_generic_response(response_formatter)


@user_router.post('/user/reset-password')
@inject
async def reset_password(
    reset_user: ResetUser,
    response_formatter: ResponseFormatterDep,
    token_service: TokenServiceDep,
    user_reset_cache: CommonCacheDep,
    user_repository: UserRepositoryDep,
    user_service: UserServiceDep,
    recaptcha_service: RecaptchaServiceDep,
):
    is_recaptcha_valid, recaptcha_error = await recaptcha_service.verify(
        reset_user.recaptcha_token, action=RECAPTCHA_ACTION_RESET_PASSWORD
    )
    if not is_recaptcha_valid:
        return _recaptcha_failure_response(response_formatter, recaptcha_error)

    try:
        decoded = token_service.decode_token(reset_user.secret_token)
    except jwt.ExpiredSignatureError:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse(
                'The password reset link has expired. Please request a new one.'
            ),
        )
    except jwt.PyJWTError as exc:
        logger.warning(f'Rejected password reset token: {exc}')
        return _password_reset_invalid_response(response_formatter)

    # Production verify failure returns {} rather than raising, and a token
    # minted for another purpose must not be spendable here.
    if not decoded or decoded.get('purpose') != PASSWORD_RESET_TOKEN_PURPOSE:
        return _password_reset_invalid_response(response_formatter)
    code = decoded.get('code')
    if not code:
        return _password_reset_invalid_response(response_formatter)

    # pop_str is GETDEL: two concurrent requests cannot both win the token.
    # The token is burned before the write, so a failed update means
    # requesting a fresh link — that is the price of a single-use guarantee.
    existing_user_id = user_reset_cache.pop_str(code)
    if not existing_user_id:
        return _password_reset_invalid_response(response_formatter)

    user = await user_repository.find_one(id=existing_user_id)
    if not user or user.deleted:
        return _password_reset_invalid_response(response_formatter)

    hashed_password = hash_password(reset_user.new_password)
    await user_repository.find_one_and_update(
        {'id': existing_user_id}, password=hashed_password
    )
    user_reset_cache.remove(password_reset_latest_key(str(existing_user_id)))
    await user_service.invalidate_user_sessions(str(existing_user_id))
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Your password has been updated successfully.'}
        ),
    )


@user_router.get('/whoami')
@inject
async def get_resources(
    request: Request,
    response_formatter: ResponseFormatterDep,
    user_repository: UserRepositoryDep,
    user_service: UserServiceDep,
):
    role_id, user_id, _ = get_current_user(request)
    user = await user_repository.find_one(id=user_id)

    if not user:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('User not found'),
        )

    is_admin = await check_is_admin(role_id)

    # Console resources are the user's UI identity marker (e.g. admin_resource),
    # so they always stay role-based.
    console_resources = await user_service.get_user_resources(
        user_id=user_id, scope=ResourceScope.CONSOLE
    )

    # Admins have implicit access to every dashboard, so they receive the full
    # list; non-admins only get the dashboards their roles grant.
    if is_admin:
        dashboards: List[Resource] = await user_service.get_all_resources(
            scope=ResourceScope.DASHBOARD
        )
        routes: List[Resource] = []
        data: List[Resource] = []
    else:
        dashboards = await user_service.get_user_resources(
            user_id=user_id, scope=ResourceScope.DASHBOARD
        )
        routes = await user_service.get_user_resources(
            user_id=user_id, scope=ResourceScope.ROUTE
        )
        data = await user_service.get_user_resources(
            user_id=user_id, scope=ResourceScope.DATA
        )

    resource = {
        'console_resources': [res.to_dict() for res in console_resources],
        'dashboards': [res.to_dict() for res in dashboards],
        'routes': [res.to_dict() for res in routes],
        'data': [res.to_dict() for res in data],
    }

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'user': user.to_dict(), 'resource': resource}
        ),
    )


@user_router.patch('/users/{user_id}/unblock')
@inject
async def unblock_user(
    request: Request,
    response_formatter: ResponseFormatterDep,
    account_lockout_service: AccountLockoutServiceDep,
    user_id: str = Path(..., description='User id to unblock', max_length=100),
):
    role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)

    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )

    if not is_valid_uuid(user_id):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'Invalid user id: {user_id}'
            ),
        )

    try:
        # Attempt to unblock user
        success = await account_lockout_service.admin_unblock_user(user_id)

        if not success:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=response_formatter.buildErrorResponse(
                    f'User with user_id {user_id} not found'
                ),
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {
                    'message': f'User account with user_id {user_id} has been successfully unblocked'
                }
            ),
        )
    except Exception as e:
        logger.error(f'Error unblocking user with user_id {user_id}: {e}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                'Failed to unblock user account'
            ),
        )
