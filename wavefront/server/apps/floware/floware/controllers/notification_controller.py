from uuid import UUID

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from db_repo_module.models.notification_users import NotificationUser
from db_repo_module.models.notifications import Notification
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import Depends
from fastapi import Query
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

from floware.di.application_container import ApplicationContainer
from floware.services.notification_service import NotificationService

notification_router = APIRouter()


@notification_router.get('/v1/notifications')
@inject
async def get_notifications(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=25),
    unseen_only: bool = False,
    notification_service: NotificationService = Depends(
        Provide[ApplicationContainer.notification_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """List notifications, newest first, each with its structured `data`.

    Paginated rather than returning the table: producers now write a row per
    mutating datasource request, so the unbounded listing this replaced would
    have grown without limit.
    """
    current_id = request.state.session.user_id
    notification_res = await notification_service.fetch_notification(
        user_id=current_id, limit=limit, offset=offset, unseen_only=unseen_only
    )
    total = await notification_service.count_notifications(
        user_id=current_id, unseen_only=unseen_only
    )

    response = [
        {
            'id': str(notify['notification_id']),
            'title': notify['title'],
            'type': notify['type'],
            # Already jsonb primitives on the way out; null for rows written
            # before the column existed, and for producers that send none.
            'data': notify['data'],
            'created_at': str(notify['created_at']),
            'updated_at': str(notify['updated_at']),
            'user_id': str(current_id),
            'seen': notify['seen'] if notify['seen'] else False,
        }
        for notify in notification_res
    ]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'notifications': response,
                'count': len(response),
                'total': total,
                'offset': offset,
                'limit': limit,
            }
        ),
    )


@notification_router.patch('/v1/notifications/{notification_id}')
@inject
async def updateNotification(
    notification_id: str,
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    notification_user_repository: SQLAlchemyRepository[NotificationUser] = Depends(
        Provide[ApplicationContainer.notification_user_repository]
    ),
    notification_repository: SQLAlchemyRepository[Notification] = Depends(
        Provide[ApplicationContainer.notification_repository]
    ),
):
    """Mark one notification seen for the calling user.

    The id is a path segment: it identifies the resource being modified, and
    only `seen` is settable, so there is nothing else for a body or query to
    carry. Named for the resource rather than `id`, matching
    `{audit_log_id}` on the audit routes.
    """
    # Parsed rather than merely validated, and the parsed value is what gets
    # sent. uuid.UUID is more permissive than the uuid column: it strips braces
    # and a urn:uuid: prefix and accepts unhyphenated hex, so forms exist that
    # pass a validity check but Postgres then rejects -- an unbalanced trailing
    # '}' from an unsubstituted URL template among them. Validating one string
    # and querying with another leaves exactly that gap, so the canonical form is
    # what reaches the repository.
    try:
        canonical_id = str(UUID(notification_id))
    except (ValueError, AttributeError, TypeError):
        # Otherwise the column raises InvalidTextRepresentation, which surfaces
        # as a 500 with a SQL traceback instead of the 400 it should have been.
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'Invalid notification id: {notification_id}'
            ),
        )

    # notification_user.notification_id is a foreign key, so writing a marker for
    # a notification that does not exist violates it and fails as a 500. Checked
    # first so a stale or mistyped id is the 404 it should be.
    if not await notification_repository.find_one(id=canonical_id):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Notification not found: {canonical_id}'
            ),
        )

    current_id = request.state.session.user_id
    await notification_user_repository.upsert(
        {'notification_id': canonical_id, 'user_id': current_id}, seen=True
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'updated successfully'}
        ),
    )
