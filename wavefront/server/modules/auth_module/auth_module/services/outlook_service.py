from datetime import datetime
import re
from typing import Dict, List, Optional
import uuid

from azure.identity.aio import ClientSecretCredential
from bs4 import BeautifulSoup
from common_module.log.logger import logger
from db_repo_module.cache.cache_manager import CacheManager
from kiota_abstractions.base_request_configuration import RequestConfiguration
import msal
from msgraph import GraphServiceClient
from msgraph.generated.models.subscription import Subscription
from flo_cloud.message_queue import MessageQueueManager
from flo_cloud.cloud_storage import CloudStorageManager
from msgraph.generated.users.item.messages.messages_request_builder import (
    MessagesRequestBuilder,
)
from pydantic import BaseModel
from pydantic import Field


class EmailAddress(BaseModel):
    name: str
    email: str


class Message(BaseModel):
    id: str
    created_date_time: str
    last_modified_date_time: Optional[str] = None
    subject: str
    body: str
    from_: EmailAddress = Field(alias='from')
    to_recipients: List[EmailAddress]
    sent_date_time: Optional[str] = None
    received_date_time: Optional[str] = None
    conversation_id: str
    web_link: str

    class Config:
        populate_by_name = True


class OutlookService:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        tenant_id: str,
        email_id: str,
        authority: str,
        webhook_url: str,
        active_subscriptions: Dict,
        cache_manager: CacheManager,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.email_id = email_id
        self.authority = authority
        self.webhook_url = webhook_url
        self.active_subscriptions = active_subscriptions
        self.app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=self.authority + self.tenant_id,
            client_credential=self.client_secret,
        )
        self.credential = ClientSecretCredential(
            tenant_id=self.tenant_id,
            client_id=self.client_id,
            client_secret=self.client_secret,
        )
        self.cache_manager = cache_manager

    async def create_subscription(self, user_email: str) -> Optional[Dict]:
        """Create a subscription for a specific user"""

        from datetime import datetime
        from datetime import timedelta

        expiration_date = datetime.utcnow() + timedelta(days=3)
        expiration_datetime = expiration_date.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        client_state = str(uuid.uuid4())
        subscription = Subscription(
            change_type='created,updated',  # Or "updated,deleted"
            notification_url=self.webhook_url,
            resource=f'/users/{user_email}/messages',
            expiration_date_time=expiration_datetime,
            client_state=client_state,
        )
        graph_client = GraphServiceClient(
            self.credential, scopes=['https://graph.microsoft.com/.default']
        )
        subscriptions = await graph_client.subscriptions.get()
        if subscriptions.value:
            return None
        response = await graph_client.subscriptions.post(subscription)
        self.active_subscriptions = response.id
        return response

    async def get_email_details(
        self,
        user_email: str,
        message_queue: MessageQueueManager,
        cloud_storage: CloudStorageManager,
        config: dict,
        existing_kb=None,
    ):
        try:
            graph_client = GraphServiceClient(
                self.credential, scopes=['https://graph.microsoft.com/.default']
            )
            created_timestamp = self.cache_manager.get_str('created_date_time')
            all_messages = []
            if created_timestamp:
                filter_datetime = datetime.fromisoformat(created_timestamp)
                # Add 1 second to exclude the exact timestamp
                formatted_timestamp = filter_datetime.isoformat().replace('+00:00', 'Z')
                query_params = (
                    MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
                        orderby=['createdDateTime desc'],
                        filter=f'createdDateTime gt {formatted_timestamp}',
                    )
                )
            else:
                query_params = (
                    MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
                        orderby=['createdDateTime desc'], top=50
                    )
                )
            request_configuration = RequestConfiguration(
                query_parameters=query_params,
            )
            response = await graph_client.users.by_user_id(user_email).messages.get(
                request_configuration=request_configuration
            )
            if not response.value:
                return False
            latest_created_time = response.value[0].created_date_time.isoformat()
            created_time = response.value[-1].created_date_time.isoformat()
            batch_messages = response.value
            all_messages.append(batch_messages)
            await self._process_and_publish_emails(
                batch_messages,
                user_email,
                message_queue,
                cloud_storage,
                config,
                existing_kb,
                latest_created_time,
                created_timestamp,
            )
            while response.odata_next_link:
                filter_datetime = datetime.fromisoformat(created_time)
                formatted_timestamp = filter_datetime.isoformat().replace('+00:00', 'Z')
                query_params = (
                    MessagesRequestBuilder.MessagesRequestBuilderGetQueryParameters(
                        orderby=['createdDateTime desc'],
                        filter=f'createdDateTime lt {formatted_timestamp}',
                    )
                )
                request_configuration = RequestConfiguration(
                    query_parameters=query_params,
                )
                response = await graph_client.users.by_user_id(user_email).messages.get(
                    request_configuration=request_configuration
                )
                if not response.value:
                    break
                batch_messages = response.value
                all_messages.append(batch_messages)
                await self._process_and_publish_emails(
                    batch_messages,
                    user_email,
                    message_queue,
                    cloud_storage,
                    config,
                    existing_kb,
                    latest_created_time,
                    created_timestamp,
                )
                latest_created_time = response.value[0].created_date_time.isoformat()
                created_time = response.value[-1].created_date_time.isoformat()
            # After processing all batches, update the cache with the latest created_date_time
            if all_messages:
                self.cache_manager.add(
                    'created_date_time',
                    all_messages[0][0].created_date_time.isoformat(),
                )
            return True

        except Exception as e:
            logger.info(f'Failed to get email details: {str(e)}')
            return False

    def _build_message_dict(self, batch_messages):
        messages = []
        for message in batch_messages:
            message_data = {
                'id': message.id,
                'created_date_time': message.created_date_time.isoformat(),
                'last_modified_date_time': message.last_modified_date_time.isoformat()
                if message.last_modified_date_time
                else None,
                'subject': message.subject,
                'body': message.body.content,
                'from': EmailAddress(
                    name=message.from_.email_address.name,
                    email=message.from_.email_address.address,
                ),
                'to_recipients': [
                    EmailAddress(
                        name=recipient.email_address.name,
                        email=recipient.email_address.address,
                    )
                    for recipient in message.to_recipients
                ],
                'sent_date_time': message.sent_date_time.isoformat()
                if message.sent_date_time
                else None,
                'received_date_time': message.received_date_time.isoformat()
                if message.received_date_time
                else None,
                'conversation_id': message.conversation_id,
                'web_link': message.web_link,
            }
            messages.append(Message(**message_data))
        return messages

    async def _process_and_publish_emails(
        self,
        batch_messages,
        user_email,
        message_queue: MessageQueueManager,
        cloud_storage: CloudStorageManager,
        config: dict,
        existing_kb,
        created_timestamp,
        timestamp,
    ):
        messages = self._build_message_dict(batch_messages)
        for message in messages:
            if (
                message.from_.email == user_email
                or message.created_date_time == created_timestamp
                if timestamp
                else False
            ):
                continue
            gcs_file_name = (
                f'kb_{existing_kb.id}/{message.id}/{message.conversation_id}'
            )
            # Get bucket name from config
            bucket_name = (
                config['gcp']['gcp_asset_storage_bucket']
                if config['cloud_config']['cloud_provider'] == 'gcp'
                else config['aws']['aws_asset_storage_bucket']
            )

            # Get topic/queue URL from config
            topic_id = (
                config['gcp']['email_topic_id']
                if config['cloud_config']['cloud_provider'] == 'gcp'
                else config['aws']['queue_url']
            )

            data = {
                'bucket': bucket_name,
                'name': gcs_file_name,
                'kb_id': str(existing_kb.id),
                'doc_id': str(''),
                'parse_type': 'email',
                'conversation_id': message.conversation_id,
                'conversation_content': self.__clean_email_content(message.body),
            }
            message_queue.add_message(
                message_body=data, topic_name_or_queue_url=topic_id
            )

    async def delete_all_subscriptions(self, user_email: str) -> List[str]:
        """
        Delete all subscriptions associated with a specific user email

        Args:
            credential: The credentials used to authenticate with Microsoft Graph
            user_email: The email address of the user whose subscriptions are being deleted

        Returns:
            List[str]: List of deleted subscription IDs
        """
        try:
            graph_client = GraphServiceClient(
                self.credential, scopes=['https://graph.microsoft.com/.default']
            )
            subscriptions = await graph_client.subscriptions.get()
            deleted_ids = []
            for subscription in subscriptions.value:
                if f'/users/{user_email}/messages' in subscription.resource:
                    try:
                        await graph_client.subscriptions.by_subscription_id(
                            subscription.id
                        ).delete()
                        deleted_ids.append(subscription.id)
                        if subscription.id in self.active_subscriptions:
                            del self.active_subscriptions[subscription.id]

                    except Exception as e:
                        logger.info(
                            f'Failed to delete subscription {subscription.id}: {str(e)}'
                        )

            logger.info(f'Deleted {len(deleted_ids)} subscriptions for {user_email}')
            return deleted_ids

        except Exception as e:
            logger.info(f'Failed to delete subscriptions: {str(e)}')
            return []

    async def view_subscription(self):
        graph_client = GraphServiceClient(
            self.credential, scopes=['https://graph.microsoft.com/.default']
        )
        subscriptions = await graph_client.subscriptions.get()
        return subscriptions

    def __clean_email_content(self, content):
        """Remove images, links, and other non-text elements from the email content."""
        # data_content = []

        soup = BeautifulSoup(content, 'html.parser')

        for img in soup.find_all('img'):
            img.decompose()

        for a in soup.find_all('a'):
            a.unwrap()
        for script in soup(['script', 'style']):
            script.decompose()
        cleaned_content = soup.get_text(separator='\n', strip=True)

        cleaned_content = re.sub(r'\n+', '\n', cleaned_content).strip()
        return cleaned_content
