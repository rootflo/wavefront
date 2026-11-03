from authz_module import (
    Legacy,
    ResourceRef,
    define_action,
    from_path,
    is_allowed,
    requires,
)
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

from floconsole.constants.user import UserRole
from floconsole.db.models.user import User
from floconsole.db.repositories.sql_alchemy_repository import SQLAlchemyRepository
from floconsole.di.application_container import ApplicationContainer
from floconsole.services.user_service import UserService
from floconsole.authorization.require_auth import same_user
from floconsole.utils.user_utils import get_current_user
from floconsole.utils.password_utils import hash_password


user_router = APIRouter(prefix='/v1')


async def _self_or_owner(principal, resource, ctx, resolver) -> bool:
    """A console user may edit themselves; an owner may edit anyone."""
    if resource is not None and same_user(resource.id, principal.id):
        return True
    return await resolver.is_admin(principal)


SELF_OR_OWNER = Legacy.CUSTOM('self_or_owner', _self_or_owner)

# Deleting a user is open to every console user; deleting an owner is not.
define_action(
    'console:DeleteOwnerUser',
    legacy=Legacy.ADMIN,
    resource_type='console_user',
    description='Delete a user who is an owner',
)


class CreateUserRequest(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str
    role: Optional[str] = UserRole.APP_ADMIN.value


class UpdateUserRequest(BaseModel):
    password: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


@user_router.post(
    '/users',
    dependencies=[
        Depends(
            requires(
                'console:CreateUser',
                resource=from_path('console_user'),
                legacy=Legacy.ADMIN,
                deny_message='You are not authorized to create users',
            )
        )
    ],
)
@inject
async def create_user(
    user_data: CreateUserRequest,
    request: Request,
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
        role=user_data.role,
    )

    logger.info(f'User created successfully: {created_user.email}')

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {'user': created_user.to_dict()}
        ),
    )


@user_router.get(
    '/whoami',
    dependencies=[
        Depends(requires('console:GetCurrentUser', legacy=Legacy.CONSOLE_USER))
    ],
)
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


@user_router.get(
    '/users',
    dependencies=[
        Depends(
            requires(
                'console:ListUsers',
                resource=from_path('console_user'),
                legacy=Legacy.CONSOLE_USER,
            )
        )
    ],
)
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


@user_router.patch(
    '/users/{user_id}',
    dependencies=[
        Depends(
            requires(
                'console:UpdateUser',
                resource=from_path('console_user', 'user_id'),
                legacy=SELF_OR_OWNER,
                deny_message='You are not authorized to edit this user',
            )
        )
    ],
)
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
):
    # Filter out None values
    update_data = {k: v for k, v in user_data.model_dump().items() if v is not None}

    if not update_data:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse('No fields to update'),
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


@user_router.delete(
    '/users/{user_id}',
    dependencies=[
        Depends(
            requires(
                'console:DeleteUser',
                resource=from_path('console_user', 'user_id'),
                legacy=Legacy.CONSOLE_USER,
            )
        )
    ],
)
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
):
    # Get current user
    _, current_user_id, _ = get_current_user(request)

    # Get target user
    target_user = await user_repository.find_one(id=user_id, deleted=False)

    if not target_user:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('User not found'),
        )

    # Prevent self-deletion
    if str(user_id) == str(current_user_id):
        logger.warning(f'User {current_user_id} attempted to delete themselves')
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'You cannot delete your own account'
            ),
        )

    target_is_owner = target_user.role == UserRole.OWNER.value

    # Authorization: normal users cannot delete owners
    if target_is_owner and not await is_allowed(
        request, 'console:DeleteOwnerUser', ResourceRef('console_user', str(user_id))
    ):
        logger.warning(f'User {current_user_id} attempted to delete owner {user_id}')
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'You are not authorized to delete owner users'
            ),
        )

    # Check minimum owner constraint
    if target_is_owner:
        owner_count = await user_service.count_owners()
        if owner_count <= 1:
            logger.warning('Cannot delete last owner user')
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'Cannot delete the last owner user'
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
