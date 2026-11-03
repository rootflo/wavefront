from datetime import datetime
from typing import Optional

from common_module.response_formatter import ResponseFormatter
from db_repo_module.models.role import Role
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import Request
from fastapi import status
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from user_management_module.constants.auth import ADMIN_ROLE_NAME
from user_management_module.constants.auth import MANAGER_ROLE_NAME
from user_management_module.constants.auth import SERVICE_AUTH_ROLE_ID
from user_management_module.services.account_lockout_service import (
    AccountLockoutService,
)
from user_management_module.user_container import UserContainer


def normalize_email(email: str) -> str:
    """Canonical email form for Floware: trimmed lowercase.

    All auth and user lookups must use this so mixed-case credentials still
    resolve after the DB stores only lowercase addresses.
    """
    return str(email).strip().lower()


def get_current_user(req: Request):
    """(role_id, user_id, session_id) of the authenticated caller."""
    principal = req.state.principal
    return principal.role_id, principal.id, principal.session_id


async def _role_name(
    role_id: str, role_repository: SQLAlchemyRepository[Role]
) -> Optional[str]:
    role = await role_repository.find_one(id=role_id)
    return role.name if role else None


@inject
async def check_is_admin(
    role_id: str,
    role_repository: SQLAlchemyRepository[Role] = Depends(
        Provide[UserContainer.role_repository]
    ),
) -> bool:
    """Whether ``role_id`` is the admin role.

    Only the default authorizer's legacy resolver calls this: routes and
    handlers ask for an action instead. Service identities
    (mTLS/passthrough/service-to-service) carry the SERVICE_AUTH_ROLE_ID and are
    always treated as admins.
    """
    if role_id == SERVICE_AUTH_ROLE_ID:
        return True

    return await _role_name(role_id, role_repository) == ADMIN_ROLE_NAME


@inject
async def check_is_manager(
    role_id: str,
    role_repository: SQLAlchemyRepository[Role] = Depends(
        Provide[UserContainer.role_repository]
    ),
) -> bool:
    """True when the session role is the built-in manager role.

    Service identities are admins, not managers, so they take the admin path
    and are never group-scoped by it.
    """
    if role_id == SERVICE_AUTH_ROLE_ID:
        return False

    return await _role_name(role_id, role_repository) == MANAGER_ROLE_NAME


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
