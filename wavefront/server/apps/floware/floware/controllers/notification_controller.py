from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from db_repo_module.models.notification_users import NotificationUser
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import Depends
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

from floware.di.application_container import ApplicationContainer
from floware.services.notification_service import NotificationService

notification_router = APIRouter()


@notification_router.get('/notification')
@inject
async def get_notifications(
    request: Request,
    notification_service: NotificationService = Depends(
        Provide[ApplicationContainer.notification_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    notification_res = []
    current_id = request.state.session.user_id
    notification_res = await notification_service.fetch_notification(user_id=current_id)

    response = [
        {
            'id': str(notify['notification_id']),
            'title': notify['title'],
            'type': notify['type'],
            'created_at': str(notify['created_at']),
            'updated_at': str(notify['updated_at']),
            'user_id': str(current_id),
            'seen': notify['seen'] if notify['seen'] else False,
        }
        for notify in notification_res
    ]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'notifications': response}),
    )


@notification_router.patch('/notification')
@inject
async def updateNotification(
    id: str,
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    notification_user_repository: SQLAlchemyRepository[NotificationUser] = Depends(
        Provide[ApplicationContainer.notification_user_repository]
    ),
):
    current_id = request.state.session.user_id
    await notification_user_repository.upsert(
        {'notification_id': id, 'user_id': current_id}, seen=True
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'updated successfully'}
        ),
    )
