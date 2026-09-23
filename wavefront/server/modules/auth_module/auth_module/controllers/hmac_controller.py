import secrets
import uuid

from auth_module.auth_container import AuthContainer
from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from db_repo_module.models.auth_secrets import AuthSecrets
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import Depends
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter
from user_management_module.utils.user_utils import check_is_admin

hmac_router = APIRouter()


@hmac_router.post('/v1/developer/secrets')
@inject
async def generate_hmac_secret(
    request: Request,
    auth_secrets_repository: SQLAlchemyRepository[AuthSecrets] = Depends(
        Provide[AuthContainer.auth_secrets_repository]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """Generate a new HMAC client key and secret pair."""
    role_id = request.state.session.role_id

    is_admin = await check_is_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse('Admin access required'),
        )

    # Generate cryptographically secure random values
    client_key = f'hmac_{uuid.uuid4().hex[:16]}'
    client_secret = secrets.token_hex(32)  # 64 character hex string

    # Store in database
    auth_secret = await auth_secrets_repository.create(
        client_key=client_key, client_secret=client_secret
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'client_key': auth_secret.client_key,
                'client_secret': auth_secret.client_secret,
                'created_at': auth_secret.created_at.isoformat(),
            }
        ),
    )
