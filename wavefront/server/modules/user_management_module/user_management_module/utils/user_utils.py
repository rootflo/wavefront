from datetime import datetime
from typing import Optional

from common_module.response_formatter import ResponseFormatter
import uuid
from typing import Union
from db_repo_module.models.role import Role
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import Request
from fastapi import status
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from user_management_module.services.account_lockout_service import (
    AccountLockoutService,
)
from user_management_module.user_container import UserContainer


def get_current_user(req: Request):
    return (
        req.state.session.role_id,
        req.state.session.user_id,
        req.state.session.session_id
        if hasattr(req.state, 'session') and req.state.session
        else None,
    )


@inject
async def check_is_admin(
    role_id: str,
    role_repository: SQLAlchemyRepository[Role] = Depends(
        Provide[UserContainer.role_repository]
    ),
) -> bool:
    role = await role_repository.find_one(id=role_id)

    if not role:
        return False

    return role.name == 'admin'


def create_account_lockout_response(
    locked_until: Optional[datetime],
    account_lockout_service: AccountLockoutService,
    response_formatter: ResponseFormatter,
) -> JSONResponse:
    """
    Create a standardized account lockout response with remaining time information.

    Args:
        locked_until: The datetime until which the account is locked
        account_lockout_service: Service for calculating lockout time
        response_formatter: Service for formatting API responses

    Returns:
        JSONResponse with HTTP 423 status and lockout message
    """
    if locked_until:
        remaining_time = account_lockout_service.get_lockout_time_remaining(
            locked_until
        )
        hours = remaining_time // 3600
        minutes = (remaining_time % 3600) // 60
        time_msg = f'{hours}h {minutes}m' if hours > 0 else f'{minutes}m'
        error_message = f'Account locked due to multiple failed login attempts. Try again in {time_msg}'
    else:
        error_message = 'Account locked due to multiple failed login attempts'

    return JSONResponse(
        status_code=status.HTTP_423_LOCKED,
        content=response_formatter.buildErrorResponse(error_message),
    )


def get_session_cache_key(session_id: Union[str, uuid.UUID]) -> str:
    return f'session_{str(session_id)}'
