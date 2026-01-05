import secrets
from typing import Optional

from auth_module.auth_container import AuthContainer
from auth_module.services.token_service import TokenService
from common_module.common_cache import CommonCache
from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from db_repo_module.models.resource import Resource
from db_repo_module.models.resource import ResourceScope
from db_repo_module.models.role import Role
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.models.user import User
from db_repo_module.models.user_role import UserRole
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.cache.cache_manager import CacheManager
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import Path, Query
from fastapi import Request
from fastapi import status
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy import and_
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy import or_
from sqlalchemy import func

from user_management_module.models.user_schema import NewUser
from user_management_module.models.user_schema import ResetUser
from user_management_module.models.user_schema import UpdateUser
from user_management_module.services.email_service import EmailService
from user_management_module.services.account_lockout_service import (
    AccountLockoutService,
)
from user_management_module.user_container import UserContainer
from user_management_module.utils.password_utils import hash_password
from user_management_module.utils.user_utils import (
    check_is_admin,
    create_account_lockout_response,
)
from user_management_module.utils.user_utils import get_current_user
from user_management_module.services.user_service import UserService
import json
from typing import List
from common_module.utils.serializer import serialize_values

user_router = APIRouter(prefix='/v1')

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='token')


@user_router.post('/users')
@inject
async def create_user(
    new_user: NewUser,
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[UserContainer.user_repository]
    ),
    role_repository: SQLAlchemyRepository[Role] = Depends(
        Provide[UserContainer.role_repository]
    ),
    user_service: UserService = Depends(Provide[UserContainer.user_service]),
):
    role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)

    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )

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

    async with user_repository.session() as session:
        try:
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

            if role_id in new_user.role_id:  # Is creating admin user
                all_roles = await role_repository.find()
                user_roles = [
                    UserRole(user_id=user_id, role_id=role.id) for role in all_roles
                ]
            else:  # Is creating user with role other than admin
                user_roles = [
                    UserRole(user_id=user_id, role_id=role_id)
                    for role_id in new_user.role_id
                ]
            session.add_all(user_roles)

            await session.commit()
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
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    user_role_repository: SQLAlchemyRepository[UserRole] = Depends(
        Provide[UserContainer.user_role_repository]
    ),
    cache_manager: CacheManager = Depends(Provide[UserContainer.cache_manager]),
):
    role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)

    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )

    async with user_role_repository.session() as session:
        # Check for valid roles
        query = select(Role).where(Role.id.in_(update_user.add_role_ids))
        result = await session.execute(query)
        existing_roles = result.scalars().all()
        existing_role_ids = {str(role.id) for role in existing_roles}

        invalid_roles = set(update_user.add_role_ids) - existing_role_ids
        if invalid_roles:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    f'Invalid role IDs: {", ".join(invalid_roles)}'
                ),
            )

        admins = await user_role_repository.find(role_id=role_id)
        if len(admins) == 1 and str(update_user.user_id) == str(admins[0].user_id):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    error='Atleast one admin is mandatory, please assign another user as admin before updating this user.'
                ),
            )

        user_roles = [
            UserRole(user_id=update_user.user_id, role_id=id)
            for id in update_user.add_role_ids
        ]
        session.add_all(user_roles)

        if (
            update_user.delete_role_ids is not None
            and len(update_user.delete_role_ids) > 0
        ):
            query = delete(UserRole.__table__).where(
                and_(
                    UserRole.user_id == update_user.user_id,
                    UserRole.role_id.in_(update_user.delete_role_ids),
                )
            )
            await session.execute(query)
        await session.commit()

    # Invalidate all user_data cache entries
    cache_manager.invalidate_query('user_data_*')
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
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[UserContainer.user_repository]
    ),
    cache_manager: CacheManager = Depends(Provide[UserContainer.cache_manager]),
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


@user_router.delete('/users')
@inject
async def delete_user(
    request: Request,
    delete_id: str = Query(alias='id'),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    user_role_repository: SQLAlchemyRepository[UserRole] = Depends(
        Provide[UserContainer.user_role_repository]
    ),
    user_service: UserService = Depends(Provide[UserContainer.user_service]),
    cache_manager: CacheManager = Depends(Provide[UserContainer.cache_manager]),
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
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[UserContainer.user_repository]
    ),
    user_reset_cache: CommonCache = Depends(Provide[CommonContainer.cache_manager]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    token_service: TokenService = Depends(Provide[AuthContainer.token_service]),
    config=Depends(Provide[UserContainer.config]),
    email_service: EmailService = Depends(Provide[UserContainer.email_service]),
    account_lockout_service: AccountLockoutService = Depends(
        Provide[UserContainer.account_lockout_service]
    ),
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
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    token_service: TokenService = Depends(Provide[AuthContainer.token_service]),
    user_reset_cache: CommonCache = Depends(Provide[CommonContainer.cache_manager]),
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[UserContainer.user_repository]
    ),
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
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[UserContainer.user_repository]
    ),
):
    _, user_id, _ = get_current_user(request)
    user = await user_repository.find_one(id=user_id)

    if not user:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('User not found'),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'user': user.to_dict()}),
    )


@user_router.patch('/users/{user_id}/unblock')
@inject
async def unblock_user(
    user_id: str = Path(..., description='User id to unblock'),
    request: Request = ...,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    account_lockout_service: AccountLockoutService = Depends(
        Provide[UserContainer.account_lockout_service]
    ),
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
