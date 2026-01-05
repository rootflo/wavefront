from typing import Optional

from auth_module.auth_container import AuthContainer
from auth_module.services.outlook_service import OutlookService
from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from db_repo_module.models.knowledge_bases import KnowledgeBase
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from fastapi.responses import PlainTextResponse
from fastapi.routing import APIRouter
from knowledge_base_module.knowledge_base_container import KnowledgeBaseContainer
from flo_cloud.message_queue import MessageQueueManager
from flo_cloud.cloud_storage import CloudStorageManager
from pydantic import BaseModel
from pydantic import RootModel

subscription_controller = APIRouter()


# Models
class SubscriptionRequest(BaseModel):
    user_email: str


class ResourceData(RootModel):
    root: dict


class Notification(BaseModel):
    subscriptionId: str
    resourceData: ResourceData | None = None


class WebhookNotificationPayload(BaseModel):
    value: list[Notification]


def serialize_subscription(subscription):
    return {
        'id': subscription.id,
        'application_id': subscription.application_id,
        'change_type': subscription.change_type,
        'client_state': subscription.client_state,
        'creator_id': subscription.creator_id,
        'notification_url': subscription.notification_url,
        'resource': subscription.resource,
    }


# Endpoint to receive webhook notifications
@subscription_controller.post('/v1/data-sources/outlook/webhook/email_received')
@inject
async def receive_notification(
    request: Request,
    payload: Optional[WebhookNotificationPayload] = None,
    service: OutlookService = Depends(Provide[AuthContainer.outlook_service]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    message_queue: MessageQueueManager = Depends(
        Provide[KnowledgeBaseContainer.message_queue]
    ),
    cloud_storage: CloudStorageManager = Depends(
        Provide[KnowledgeBaseContainer.cloud_storage]
    ),
    knowledge_base_repository: SQLAlchemyRepository[KnowledgeBase] = Depends(
        Provide[KnowledgeBaseContainer.knowledge_base_repository]
    ),
    config=Depends(Provide[KnowledgeBaseContainer.config]),
):
    # Check for validation token in query parameters
    validation_token = request.query_params.get('validationToken')
    if validation_token:
        return PlainTextResponse(content=validation_token)
    # Process the notification payload
    try:
        existing_kb = await knowledge_base_repository.find_one(name='email')
        if not existing_kb:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'Knowledge Base with the given id does not exist'
                ),
            )
        notifications = payload.value
        for notification in notifications:
            subscription_id = notification.subscriptionId
            result = await service.view_subscription()
            active_subs = result.value[0].id
            if subscription_id in active_subs:
                # This is a valid notification
                resource_data = (
                    notification.resourceData.root if notification.resourceData else {}
                )
                user_email = result.value[0].resource.split('/')[2]

                if resource_data.get('@odata.type') == '#Microsoft.Graph.Message':
                    content = await service.get_email_details(
                        user_email, message_queue, cloud_storage, config, existing_kb
                    )
        if content:
            return JSONResponse(
                content={'status': 'notification received'}, status_code=202
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'There is no message present for the user'
                ),
            )
    except Exception as e:
        print(f'Error processing notification: {str(e)}')
        raise HTTPException(status_code=500, detail='Invalid request')


# Endpoint to create a new subscription
@subscription_controller.post('/v1/data-sources/outlook/subscription')
@inject
async def create_subscription(
    subscription_req: SubscriptionRequest,
    service: OutlookService = Depends(Provide[AuthContainer.outlook_service]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    try:
        result = await service.create_subscription(subscription_req.user_email)
        if result:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=response_formatter.buildSuccessResponse(
                    {
                        'message': 'Created the subsription',
                    }
                ),
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    f'Subscription already created for the user {subscription_req.user_email}'
                ),
            )
    except Exception as e:
        print(e)


@subscription_controller.delete('/v1/data-sources/outlook/subscription/delete')
@inject
async def delete_subscription(
    subscription_req: SubscriptionRequest,
    service: OutlookService = Depends(Provide[AuthContainer.outlook_service]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    try:
        deleted_subscriptions = await service.delete_all_subscriptions(
            subscription_req.user_email
        )
        if deleted_subscriptions:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=response_formatter.buildSuccessResponse(
                    {
                        'message': f'Subscriptions are deleted for these ids {deleted_subscriptions}',
                    }
                ),
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'There is no subscription present to delete for the user'
                ),
            )
    except Exception as e:
        print(f'Error deleting subscriptions: {str(e)}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to delete subscriptions: {str(e)}',
        )


@subscription_controller.get('/v1/data-sources/outlook/subscriptions')
@inject
async def get_subscription(
    service: OutlookService = Depends(Provide[AuthContainer.outlook_service]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    try:
        result = await service.view_subscription()
        if result.value:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=response_formatter.buildSuccessResponse(
                    {
                        'message': 'These are the subscriptions',
                        'data': [serialize_subscription(sub) for sub in result.value],
                    }
                ),
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'There is no subscription created for the user'
                ),
            )
    except Exception as e:
        print(f'Error deleting subscriptions: {str(e)}')
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f'Failed to delete subscriptions: {str(e)}',
        )
