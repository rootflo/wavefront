import secrets
import uuid
from typing import List, Optional

from common_module.log.logger import logger
from db_repo_module.models.resource import Resource
from db_repo_module.models.resource import ResourceScope
from db_repo_module.models.role import Role
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.models.user import User
from db_repo_module.models.user_role import UserRole
from dependency_injector.wiring import inject
from fastapi import Path, Query
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy import and_
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy import or_
from sqlalchemy import func

from user_management_module.dependencies.injection import (
    AccountLockoutServiceDep,
    CacheManagerDep,
    CommonCacheDep,
    EmailServiceDep,
    ResponseFormatterDep,
    TokenServiceDep,
    UserConfigDep,
    UserRepositoryDep,
    UserRoleRepositoryDep,
    UserServiceDep,
)
from user_management_module.models.user_schema import NewUser
from user_management_module.models.user_schema import ResetUser
from user_management_module.models.user_schema import UpdateUser
from user_management_module.utils.password_utils import hash_password
from user_management_module.utils.user_utils import (
    check_is_admin,
    create_account_lockout_response,
)
from user_management_module.utils.user_utils import get_current_user
import json
from common_module.utils.serializer import serialize_values

user_router = APIRouter(prefix='/v1')

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='token')


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

    is_creating_admin = role_id in new_user.role_id

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
            if not is_creating_admin:
                get_console_resources_query = (
                    select(Resource)
                    .join(RoleResource, Resource.id == RoleResource.resource_id)
                    .where(
                        and_(
                            RoleResource.role_id.in_(new_user.role_id),
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

            # Create user
            session.add(user)
            await session.flush()
            user_id = user.id

            user_roles = [
                UserRole(user_id=user_id, role_id=r_id) for r_id in new_user.role_id
            ]
            session.add_all(user_roles)

            await session.commit()

            cache_manager.invalidate_query('user_data_*')

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

        # Guard against demoting the only remaining admin when roles are changed.
        if add_role_ids or delete_role_ids:
            admins = await user_role_repository.find(role_id=role_id)
            if len(admins) == 1 and str(update_user.user_id) == str(admins[0].user_id):
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=response_formatter.buildErrorResponse(
                        error='Atleast one admin is mandatory, please assign another user as admin before updating this user.'
                    ),
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

        if profile_updates:
            user_in_session = await session.get(User, update_user.user_id)
            for field, value in profile_updates.items():
                setattr(user_in_session, field, value)

        await session.commit()

    # Invalidate all user_data cache entries
    cache_manager.invalidate_query('user_data_*')
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
    search: Optional[str] = Query(None, description='Search by name or email'),
    roles: Optional[List[str]] = Query(None, description='Filter by role name'),
    limit: int = Query(100),
    offset: int = Query(0),
    force_fetch: int = Query(0),
):
    role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)

    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )
    # checking the cache for the keys
    cache_key = f'user_data_{offset}_{limit}_{search}_{roles}'
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
        # Build query to combine all three tables
        # Aggregated query with roles
        query = (
            select(
                User.id,
                User.first_name,
                User.last_name,
                User.email,
                User.username,
                func.array_agg(
                    func.json_build_object(
                        'id',
                        Role.id,
                        'name',
                        Role.name,
                    )
                ).label('roles'),
            )
            .join(UserRole, User.id == UserRole.user_id)
            .join(Role, UserRole.role_id == Role.id)
            .where(User.deleted.is_(False))
            .group_by(User.id)
        )

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
            filters.append(User.username.ilike(f'%{search}%'))
            query = query.where(or_(*filters))

        # Add role filter
        if roles:
            query = query.where(Role.name.in_(roles))

        query = query.offset(offset).limit(limit)

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


@user_router.get('/users/{user_id}')
@inject
async def get_user(
    request: Request,
    response_formatter: ResponseFormatterDep,
    user_repository: UserRepositoryDep,
    cache_manager: CacheManagerDep,
    user_id: str = Path(..., description='User id to fetch'),
    force_fetch: int = Query(0),
):
    """Fetch one user by id — name and email, without roles.

    Admin only, like the listing endpoint it complements. It resolves an id the
    caller already holds (a quotation's assignee, say) rather than returning a
    page, so the console does not have to pull the whole directory to put a name
    to one id.

    Cached for an hour under a `user_data_` key, so the existing
    `invalidate_query('user_data_*')` calls in create/update/delete already clear
    it — there is no new invalidation to remember. Pass `force_fetch=1` to read
    through to the database.
    """
    role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)

    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )

    # User.id is a uuid column, so a malformed id would otherwise reach the
    # database and come back as a 500 rather than a 400.
    try:
        uuid.UUID(user_id)
    except ValueError:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'Invalid user id: {user_id}'
            ),
        )

    cache_key = f'user_data_id_{user_id}'
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

    serialize_result = {
        'id': str(user.id),
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
    }

    cache_manager.add(cache_key, json.dumps(serialize_result), expiry=60 * 60)  # 1 hour
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'user': serialize_result}),
    )


@user_router.delete('/users')
@inject
async def delete_user(
    request: Request,
    response_formatter: ResponseFormatterDep,
    user_role_repository: UserRoleRepositoryDep,
    user_service: UserServiceDep,
    cache_manager: CacheManagerDep,
    delete_id: str = Query(alias='id'),
):
    role_id, user_id, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)

    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )

    admins = await user_role_repository.find(role_id=role_id)
    if len(admins) == 1 and user_id == delete_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Atleast one admin is mandatory, please assign another user as admin before deleting this user.'
            ),
        )

    response = await user_service.delete_user(delete_id)
    # Invalidate all user_data cache entries
    cache_manager.invalidate_query('user_data_*')

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
    email: str,
    user_repository: UserRepositoryDep,
    user_reset_cache: CommonCacheDep,
    response_formatter: ResponseFormatterDep,
    token_service: TokenServiceDep,
    config: UserConfigDep,
    email_service: EmailServiceDep,
    account_lockout_service: AccountLockoutServiceDep,
):
    try:
        # checking if the user exists in the db
        user_with_email = await user_repository.find_one(email=email)
        if not user_with_email:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    error='No user found with this email ID.'
                ),
            )
        if user_with_email.deleted:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    error='No user found with this email ID.'
                ),
            )

        is_locked, locked_until = await account_lockout_service.check_account_lockout(
            email
        )
        if is_locked:
            return create_account_lockout_response(
                locked_until, account_lockout_service, response_formatter
            )

        # creating an jwt token for reseting the password
        random_digit = secrets.token_hex(16)

        decoded_url = token_service.create_token(
            payload={'code': random_digit},
            is_temporary=True,
        )

        # creating the user in the user_reset table
        user_reset_cache.add(random_digit, str(user_with_email.id), expiry=600)

        # generating the url
        forget_url_link = f'{config["web"]["url"]}/reset-password?token={decoded_url}'

        # setting up the emial part
        email_response = email_service.send_forget_password_email(
            forget_url_link, email
        )
        if email_response:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=response_formatter.buildSuccessResponse(
                    {
                        'message': 'A password reset link has been sent to your registered email address.',
                    }
                ),
            )
        else:
            logger.error('Erro while sending email')
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'An error occurred while sending the email. Please verify your email address and try again later.'
                ),
            )
    except ValueError:
        logger.error('Error in email sending credentials')
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Password reset failed. Please reach out to your administrator for assistance.'
            ),
        )


@user_router.post('/user/reset-password')
@inject
async def reset_password(
    reset_user: ResetUser,
    response_formatter: ResponseFormatterDep,
    token_service: TokenServiceDep,
    user_reset_cache: CommonCacheDep,
    user_repository: UserRepositoryDep,
):
    try:
        decoded_url = token_service.decode_token(reset_user.secret_token)
        existing_user_id = user_reset_cache.get_str(decoded_url['code'])
        if not existing_user_id:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=response_formatter.buildErrorResponse(
                    "Sorry, we couldn't verify your identity, or your password reset link has expired. Please try again or request a new reset link."
                ),
            )
        hashed_password = hash_password(reset_user.new_password)
        await user_repository.find_one_and_update(
            {'id': existing_user_id}, password=hashed_password
        )
        # removing the user from user reset table  after updating the password
        user_reset_cache.remove(decoded_url['code'])
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'message': 'Your password has been updated successfully.'}
            ),
        )
    except jwt.ExpiredSignatureError:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse(
                'The password reset link has expired. Please request a new one.'
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
    user_id: str = Path(..., description='User id to unblock'),
):
    role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)

    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
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
