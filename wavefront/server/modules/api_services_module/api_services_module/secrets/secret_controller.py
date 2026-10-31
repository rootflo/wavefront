"""Admin API for the named secrets API service definitions reference.

A value is write-only: no route returns it.
"""

from typing import Optional
from uuid import UUID

from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from user_management_module.utils.user_utils import check_is_admin

from ..api_services_container import ApiServicesContainer
from ..config.registry import ServiceRegistry
from ..utils.api_change_publisher import ApiChangePublisher, UpdateMessage
from .secret_store_service import SecretNotFound, SecretStoreService

secret_router = APIRouter()


class CreateSecretPayload(BaseModel):
    name: str
    value: str
    description: Optional[str] = None


class UpdateSecretPayload(BaseModel):
    value: Optional[str] = None
    description: Optional[str] = None


async def _forbid_non_admin(request: Request, response_formatter: ResponseFormatter):
    """None when the caller is an admin, otherwise the 403 to return."""
    is_admin = await check_is_admin(request.state.session.role_id)
    if is_admin:
        return None
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content=response_formatter.buildErrorResponse('Admin access required'),
    )


def _error(response_formatter: ResponseFormatter, status_code: int, message: str):
    return JSONResponse(
        status_code=status_code,
        content=response_formatter.buildErrorResponse(message),
    )


def _reload_referencing_services(
    secret_name: str,
    service_registry: ServiceRegistry,
    api_change_publisher: ApiChangePublisher,
) -> list:
    """Ask every pod to reload the services that use `secret_name`."""
    service_ids = service_registry.services_referencing(secret_name)
    for service_id in service_ids:
        api_change_publisher.publish_message(
            UpdateMessage(
                service_id=service_id,
                operation='update',
                metadata={'reason': 'secret_changed', 'secret': secret_name},
            )
        )
    if service_ids:
        logger.info(
            f'Secret {secret_name} changed; reloading services: {", ".join(service_ids)}'
        )
    return service_ids


@secret_router.post('/v1/secrets')
@inject
async def create_secret(
    request: Request,
    payload: CreateSecretPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    secret_store: SecretStoreService = Depends(
        Provide[ApiServicesContainer.secret_store_service]
    ),
    service_registry: ServiceRegistry = Depends(
        Provide[ApiServicesContainer.service_registry]
    ),
    api_change_publisher: ApiChangePublisher = Depends(
        Provide[ApiServicesContainer.api_change_publisher]
    ),
):
    """Create a secret. The value is stored and never returned."""
    forbidden = await _forbid_non_admin(request, response_formatter)
    if forbidden:
        return forbidden

    try:
        secret = await secret_store.create(
            name=payload.name, value=payload.value, description=payload.description
        )
    except ValueError as e:
        return _error(response_formatter, status.HTTP_400_BAD_REQUEST, str(e))
    except Exception:
        logger.exception('Failed to create secret')
        return _error(
            response_formatter,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            'Failed to create secret',
        )

    # A service that referenced this name before it existed was skipped at load.
    _reload_referencing_services(secret['name'], service_registry, api_change_publisher)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse({'secret': secret}),
    )


@secret_router.get('/v1/secrets')
@inject
async def list_secrets(
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    secret_store: SecretStoreService = Depends(
        Provide[ApiServicesContainer.secret_store_service]
    ),
):
    """List secrets, without their values."""
    forbidden = await _forbid_non_admin(request, response_formatter)
    if forbidden:
        return forbidden

    try:
        secrets = await secret_store.list()
    except Exception:
        logger.exception('Failed to list secrets')
        return _error(
            response_formatter,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            'Failed to list secrets',
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'secrets': secrets}),
    )


@secret_router.get('/v1/secrets/{secret_id}')
@inject
async def get_secret(
    request: Request,
    secret_id: UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    secret_store: SecretStoreService = Depends(
        Provide[ApiServicesContainer.secret_store_service]
    ),
    service_registry: ServiceRegistry = Depends(
        Provide[ApiServicesContainer.service_registry]
    ),
):
    """One secret, without its value, and the services that reference it."""
    forbidden = await _forbid_non_admin(request, response_formatter)
    if forbidden:
        return forbidden

    try:
        secret = await secret_store.get(secret_id)
    except SecretNotFound as e:
        return _error(response_formatter, status.HTTP_404_NOT_FOUND, str(e))
    except Exception:
        logger.exception(f'Failed to get secret {secret_id}')
        return _error(
            response_formatter,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            'Failed to get secret',
        )
    secret['referenced_by'] = service_registry.services_referencing(secret['name'])
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'secret': secret}),
    )


@secret_router.put('/v1/secrets/{secret_id}')
@inject
async def update_secret(
    request: Request,
    secret_id: UUID,
    payload: UpdateSecretPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    secret_store: SecretStoreService = Depends(
        Provide[ApiServicesContainer.secret_store_service]
    ),
    service_registry: ServiceRegistry = Depends(
        Provide[ApiServicesContainer.service_registry]
    ),
    api_change_publisher: ApiChangePublisher = Depends(
        Provide[ApiServicesContainer.api_change_publisher]
    ),
):
    """Rotate the value and/or edit the description.

    A new value reloads, on every pod, the services that reference the secret.
    """
    forbidden = await _forbid_non_admin(request, response_formatter)
    if forbidden:
        return forbidden

    try:
        secret = await secret_store.update(
            secret_id, value=payload.value, description=payload.description
        )
    except SecretNotFound as e:
        return _error(response_formatter, status.HTTP_404_NOT_FOUND, str(e))
    except ValueError as e:
        return _error(response_formatter, status.HTTP_400_BAD_REQUEST, str(e))
    except Exception:
        logger.exception(f'Failed to update secret {secret_id}')
        return _error(
            response_formatter,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            'Failed to update secret',
        )

    if payload.value is not None:
        _reload_referencing_services(
            secret['name'], service_registry, api_change_publisher
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'secret': secret}),
    )


@secret_router.delete('/v1/secrets/{secret_id}')
@inject
async def delete_secret(
    request: Request,
    secret_id: UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    secret_store: SecretStoreService = Depends(
        Provide[ApiServicesContainer.secret_store_service]
    ),
    service_registry: ServiceRegistry = Depends(
        Provide[ApiServicesContainer.service_registry]
    ),
):
    """Delete a secret. Refused with 409 while an API service references it."""
    forbidden = await _forbid_non_admin(request, response_formatter)
    if forbidden:
        return forbidden

    try:
        secret = await secret_store.get(secret_id)
    except SecretNotFound as e:
        return _error(response_formatter, status.HTTP_404_NOT_FOUND, str(e))
    except Exception:
        logger.exception(f'Failed to delete secret {secret_id}')
        return _error(
            response_formatter,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            'Failed to delete secret',
        )

    service_ids = service_registry.services_referencing(secret['name'])
    if service_ids:
        content = response_formatter.buildErrorResponse(
            f'Secret {secret["name"]} is used by API services: {", ".join(service_ids)}'
        )
        content['data'] = {'service_ids': service_ids}
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=content)

    try:
        await secret_store.delete(secret_id)
    except SecretNotFound as e:
        return _error(response_formatter, status.HTTP_404_NOT_FOUND, str(e))
    except Exception:
        logger.exception(f'Failed to delete secret {secret_id}')
        return _error(
            response_formatter,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            'Failed to delete secret',
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Secret deleted', 'secret': secret}
        ),
    )
