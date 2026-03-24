from typing import Annotated

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from floware.di.application_container import ApplicationContainer
from floware.services.scheduled_job_service import ScheduledJobService
from floware.utils.scheduled_job_schema import (
    CreateScheduledJobRequest,
    UpdateScheduledJobRequest,
)
from user_management_module.utils.user_utils import check_is_admin, get_current_user

scheduled_job_router = APIRouter(prefix='/v1/scheduled-jobs')


def _to_job_response(job):
    return {
        'id': str(job.id),
        'job_type': job.job_type,
        'cron_expr': job.cron_expr,
        'timezone': job.timezone,
        'status': job.status,
        'payload': job.payload,
        'next_run_at': str(job.next_run_at) if job.next_run_at else None,
        'last_run_at': str(job.last_run_at) if job.last_run_at else None,
        'last_error': job.last_error,
        'retry_count': job.retry_count,
        'max_retries': job.max_retries,
        'created_at': str(job.created_at) if job.created_at else None,
        'updated_at': str(job.updated_at) if job.updated_at else None,
    }


@scheduled_job_router.post('')
@inject
async def create_scheduled_job(
    request: Request,
    payload: CreateScheduledJobRequest,
    scheduled_job_service: Annotated[
        ScheduledJobService,
        Depends(Provide[ApplicationContainer.scheduled_job_service]),
    ],
    response_formatter: Annotated[
        ResponseFormatter, Depends(Provide[CommonContainer.response_formatter])
    ],
):
    role_id, _, _ = get_current_user(request)
    if not await check_is_admin(role_id):
        raise HTTPException(status_code=401, detail='Unauthorized')

    job = await scheduled_job_service.create_job(
        job_type=payload.job_type,
        cron_expr=payload.cron_expr,
        timezone_name=payload.timezone,
        payload=payload.payload,
        max_retries=payload.max_retries,
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse({'job': _to_job_response(job)}),
    )


@scheduled_job_router.get('')
@inject
async def list_scheduled_jobs(
    request: Request,
    limit: int = 100,
    job_type: str | None = None,
    job_status: str | None = None,
    query_id: str | None = None,
    datasource_id: str | None = None,
    scheduled_job_service: Annotated[
        ScheduledJobService,
        Depends(Provide[ApplicationContainer.scheduled_job_service]),
    ] = None,
    response_formatter: Annotated[
        ResponseFormatter, Depends(Provide[CommonContainer.response_formatter])
    ] = None,
):
    role_id, _, _ = get_current_user(request)
    if not await check_is_admin(role_id):
        raise HTTPException(status_code=401, detail='Unauthorized')

    payload_filters: dict[str, str] = {}
    if query_id:
        payload_filters['query_id'] = query_id
    if datasource_id:
        payload_filters['datasource_id'] = datasource_id

    jobs = await scheduled_job_service.list_jobs(
        limit=limit,
        job_type=job_type,
        status=job_status,
        payload_filters=payload_filters or None,
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'jobs': [_to_job_response(job) for job in jobs]}
        ),
    )


@scheduled_job_router.get('/{job_id}')
@inject
async def get_scheduled_job(
    request: Request,
    job_id: str,
    scheduled_job_service: Annotated[
        ScheduledJobService,
        Depends(Provide[ApplicationContainer.scheduled_job_service]),
    ] = None,
    response_formatter: Annotated[
        ResponseFormatter, Depends(Provide[CommonContainer.response_formatter])
    ] = None,
):
    role_id, _, _ = get_current_user(request)
    if not await check_is_admin(role_id):
        raise HTTPException(status_code=401, detail='Unauthorized')

    job = await scheduled_job_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Scheduled job not found')

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'job': _to_job_response(job)}),
    )


@scheduled_job_router.patch('/{job_id}')
@inject
async def update_scheduled_job(
    request: Request,
    job_id: str,
    payload: UpdateScheduledJobRequest,
    scheduled_job_service: Annotated[
        ScheduledJobService,
        Depends(Provide[ApplicationContainer.scheduled_job_service]),
    ] = None,
    response_formatter: Annotated[
        ResponseFormatter, Depends(Provide[CommonContainer.response_formatter])
    ] = None,
):
    role_id, _, _ = get_current_user(request)
    if not await check_is_admin(role_id):
        raise HTTPException(status_code=401, detail='Unauthorized')

    job = await scheduled_job_service.update_job(
        job_id=job_id,
        cron_expr=payload.cron_expr,
        timezone_name=payload.timezone,
        payload=payload.payload,
        max_retries=payload.max_retries,
        status=payload.status,
    )
    if not job:
        raise HTTPException(status_code=404, detail='Scheduled job not found')

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'job': _to_job_response(job)}),
    )


@scheduled_job_router.post('/{job_id}/pause')
@inject
async def pause_scheduled_job(
    request: Request,
    job_id: str,
    scheduled_job_service: Annotated[
        ScheduledJobService,
        Depends(Provide[ApplicationContainer.scheduled_job_service]),
    ] = None,
    response_formatter: Annotated[
        ResponseFormatter, Depends(Provide[CommonContainer.response_formatter])
    ] = None,
):
    role_id, _, _ = get_current_user(request)
    if not await check_is_admin(role_id):
        raise HTTPException(status_code=401, detail='Unauthorized')

    job = await scheduled_job_service.pause_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Scheduled job not found')
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'job': _to_job_response(job)}),
    )


@scheduled_job_router.post('/{job_id}/resume')
@inject
async def resume_scheduled_job(
    request: Request,
    job_id: str,
    scheduled_job_service: Annotated[
        ScheduledJobService,
        Depends(Provide[ApplicationContainer.scheduled_job_service]),
    ] = None,
    response_formatter: Annotated[
        ResponseFormatter, Depends(Provide[CommonContainer.response_formatter])
    ] = None,
):
    role_id, _, _ = get_current_user(request)
    if not await check_is_admin(role_id):
        raise HTTPException(status_code=401, detail='Unauthorized')

    job = await scheduled_job_service.resume_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Scheduled job not found')
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'job': _to_job_response(job)}),
    )


@scheduled_job_router.delete('/{job_id}')
@inject
async def delete_scheduled_job(
    request: Request,
    job_id: str,
    scheduled_job_service: Annotated[
        ScheduledJobService,
        Depends(Provide[ApplicationContainer.scheduled_job_service]),
    ] = None,
    response_formatter: Annotated[
        ResponseFormatter, Depends(Provide[CommonContainer.response_formatter])
    ] = None,
):
    role_id, _, _ = get_current_user(request)
    if not await check_is_admin(role_id):
        raise HTTPException(status_code=401, detail='Unauthorized')

    await scheduled_job_service.delete_job(job_id)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Scheduled job deleted successfully'}
        ),
    )
