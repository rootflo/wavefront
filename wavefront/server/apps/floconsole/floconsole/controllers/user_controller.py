from typing import Optional
from uuid import UUID

from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import APIRouter
from fastapi import Depends
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from floconsole.db.models.user import User
from floconsole.db.repositories.sql_alchemy_repository import SQLAlchemyRepository
from floconsole.di.application_container import ApplicationContainer
from floconsole.services.user_service import UserService
from floconsole.utils.user_utils import get_current_user
from floconsole.utils.password_utils import hash_password


user_router = APIRouter(prefix='/v1')


class CreateUserRequest(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str


class UpdateUserRequest(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


@user_router.post('/users')
@inject
async def create_user(
    user_data: CreateUserRequest,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[ApplicationContainer.user_repository]
    ),
):
    existing_user = await user_repository.find_one(email=user_data.email)

    if existing_user:
        logger.warning(
            f'User creation failed - email already exists: {user_data.email}'
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=response_formatter.buildErrorResponse('Email already exists'),
        )

    hashed_password = hash_password(user_data.password)

    created_user = await user_repository.create(
        email=user_data.email,
        password=hashed_password,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
    )

    logger.info(f'User created successfully: {created_user.email}')

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {'user': created_user.to_dict()}
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
        Provide[ApplicationContainer.user_repository]
    ),
):
    _, user_id, _ = get_current_user(request)
    user = await user_repository.find_one(id=user_id)

    if not user:
        logger.error(f'User not found for ID: {user_id}')
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('User not found'),
        )

    logger.info(f'User {user.email} retrieved successfully')

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'user': user.to_dict()}),
    )


@user_router.get('/users')
@inject
async def list_users(
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    user_service: UserService = Depends(Provide[ApplicationContainer.user_service]),
):
    users = await user_service.get_all_users()
    users_data = [user.to_dict() for user in users]

    logger.info(f'Retrieved {len(users)} users successfully')

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'users': users_data}),
    )


@user_router.patch('/users/{user_id}')
@inject
async def update_user(
    user_id: UUID,
    user_data: UpdateUserRequest,
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    user_service: UserService = Depends(Provide[ApplicationContainer.user_service]),
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[ApplicationContainer.user_repository]
    ),
    config: dict = Depends(Provide[ApplicationContainer.config]),
):
    # Get current user
    _, current_user_id, _ = get_current_user(request)
    super_admin_emails = config['super_admin']['email'].split(',')

    current_user = await user_repository.find_one(id=current_user_id)
    is_super_admin = current_user and current_user.email in super_admin_emails

    # Authorization: users can only edit themselves, super admins can edit anyone
    if str(user_id) != str(current_user_id) and not is_super_admin:
        logger.warning(
            f'User {current_user_id} attempted to edit user {user_id} without permission'
        )
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'You are not authorized to edit this user'
            ),
        )

    # Filter out None values
    update_data = {k: v for k, v in user_data.model_dump().items() if v is not None}

    if not update_data:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse('No fields to update'),
        )

    # Check email uniqueness if email is being updated
    if 'email' in update_data:
        existing_user = await user_repository.find_one(email=update_data['email'])
        if existing_user and str(existing_user.id) != str(user_id):
            logger.warning(
                f'Update failed - email already exists: {update_data["email"]}'
            )
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=response_formatter.buildErrorResponse('Email already exists'),
            )

    try:
        updated_user = await user_service.update_user(user_id, **update_data)

        if not updated_user:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=response_formatter.buildErrorResponse('User not found'),
            )

        logger.info(f'User {updated_user.email} updated successfully')

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'user': updated_user.to_dict()}
            ),
        )
    except Exception as e:
        logger.error(f'Failed to update user: {str(e)}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Failed to update user: {str(e)}'
            ),
        )


@user_router.delete('/users/{user_id}')
@inject
async def delete_user(
    user_id: UUID,
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    user_service: UserService = Depends(Provide[ApplicationContainer.user_service]),
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[ApplicationContainer.user_repository]
    ),
    config: dict = Depends(Provide[ApplicationContainer.config]),
):
    # Get current user
    _, current_user_id, _ = get_current_user(request)
    super_admin_emails = config['super_admin']['email'].split(',')

    current_user = await user_repository.find_one(id=current_user_id)
    is_super_admin = current_user and current_user.email in super_admin_emails

    # Get target user
    target_user = await user_repository.find_one(id=user_id, deleted=False)

    if not target_user:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('User not found'),
        )

    target_is_super_admin = target_user.email in super_admin_emails

    # Authorization: normal users cannot delete super admins
    if target_is_super_admin and not is_super_admin:
        logger.warning(
            f'User {current_user_id} attempted to delete super admin {user_id}'
        )
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'You are not authorized to delete super admin users'
            ),
        )

    # Check minimum super admin constraint
    if target_is_super_admin:
        super_admin_count = await user_service.count_super_admins(super_admin_emails)
        if super_admin_count <= 1:
            logger.warning('Cannot delete last super admin user')
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'Cannot delete the last super admin user'
                ),
            )

    try:
        deleted_user = await user_service.delete_user(user_id)

        if not deleted_user:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=response_formatter.buildErrorResponse('User not found'),
            )

        logger.info(f'User {deleted_user.email} deleted successfully')

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'message': 'User deleted successfully'}
            ),
        )
    except Exception as e:
        logger.error(f'Failed to delete user: {str(e)}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Failed to delete user: {str(e)}'
            ),
        )
