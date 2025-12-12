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
from fastapi import status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

hmac_router = APIRouter()


@hmac_router.post('/v1/developer/secrets')
@inject
async def generate_hmac_secret(
    auth_secrets_repository: SQLAlchemyRepository[AuthSecrets] = Depends(
        Provide[AuthContainer.auth_secrets_repository]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """Generate a new HMAC client key and secret pair."""
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
