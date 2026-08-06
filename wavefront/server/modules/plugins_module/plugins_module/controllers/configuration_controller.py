"""
Controller for the namespaced runtime configuration store.

Holds static reference data that deterministic workflow steps read at execution
time — thresholds, limits, lookup tables. Configurations are
addressed by (namespace, key); the row's `id` is a surrogate and no route uses
it, which also keeps `/{namespace}` unambiguous.
"""

from typing import Any, Optional

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from plugins_module.plugins_container import PluginsContainer
from plugins_module.services.configuration_service import (
    ConfigurationAlreadyExistsError,
    ConfigurationService,
    NamespaceNotFoundError,
)

configuration_router = APIRouter()


class CreateConfigurationPayload(BaseModel):
    namespace: str
    key: str
    # Arbitrary JSON document — wavefront never interprets it.
    value: Any
    description: Optional[str] = None


class UpsertConfigurationPayload(BaseModel):
    value: Any
    description: Optional[str] = None


@configuration_router.post('/v1/configurations')
@inject
async def create_configuration(
    payload: CreateConfigurationPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    configuration_service: ConfigurationService = Depends(
        Provide[PluginsContainer.configuration_service]
    ),
):
    try:
        configuration = await configuration_service.create(
            namespace=payload.namespace,
            key=payload.key,
            value=payload.value,
            description=payload.description,
        )
    except NamespaceNotFoundError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )
    except ConfigurationAlreadyExistsError as e:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=response_formatter.buildErrorResponse(str(e)),
        )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(configuration),
    )


@configuration_router.get('/v1/configurations')
@inject
async def list_configurations(
    namespace: Optional[str] = Query(None),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    configuration_service: ConfigurationService = Depends(
        Provide[PluginsContainer.configuration_service]
    ),
):
    """List configurations as metadata only — `value` is omitted, since a
    listing is for discovery and a document can be large."""
    configurations = await configuration_service.list(namespace=namespace)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'configurations': configurations}
        ),
    )


@configuration_router.get('/v1/configurations/{namespace}/{key}')
@inject
async def get_configuration(
    namespace: str,
    key: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    configuration_service: ConfigurationService = Depends(
        Provide[PluginsContainer.configuration_service]
    ),
):
    """Return the configuration document itself.

    This is the read path the `fetch_configuration` function node uses on every
    workflow run, so the body is the document and nothing else.
    """
    value = await configuration_service.get_value(namespace, key)
    if value is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f"Configuration '{key}' not found in namespace '{namespace}'"
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(value),
    )


@configuration_router.put('/v1/configurations/{namespace}/{key}')
@inject
async def upsert_configuration(
    namespace: str,
    key: str,
    payload: UpsertConfigurationPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    configuration_service: ConfigurationService = Depends(
        Provide[PluginsContainer.configuration_service]
    ),
):
    """Replace the configuration's value, creating it if absent.

    The value is replaced wholesale, not merged — a config document is edited as
    a whole, and a partial-merge rule would make it impossible to remove a field.
    """
    try:
        configuration = await configuration_service.upsert(
            namespace=namespace,
            key=key,
            value=payload.value,
            description=payload.description,
        )
    except NamespaceNotFoundError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(configuration),
    )


@configuration_router.delete('/v1/configurations/{namespace}/{key}')
@inject
async def delete_configuration(
    namespace: str,
    key: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    configuration_service: ConfigurationService = Depends(
        Provide[PluginsContainer.configuration_service]
    ),
):
    deleted = await configuration_service.delete(namespace, key)
    if not deleted:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f"Configuration '{key}' not found in namespace '{namespace}'"
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': f"Configuration '{key}' deleted from namespace '{namespace}'"}
        ),
    )
