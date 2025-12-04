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
from floconsole.utils.user_utils import get_current_user
from floconsole.utils.password_utils import hash_password


user_router = APIRouter(prefix='/v1')


class CreateUserRequest(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str


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
