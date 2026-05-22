import asyncio
import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from common_module.log.logger import logger
from google.api_core import exceptions as google_exceptions
from google.cloud import pubsub_v1
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from triggers_module.providers.base import (
    Attachment,
    NormalizedEmailEvent,
    TokenBundle,
    TriggerProvider,
)
from triggers_module.providers.gmail.gmail_oauth import GmailOAuthClient


DEFAULT_GMAIL_SCOPES: List[str] = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/userinfo.email',
]


class GmailProvider(TriggerProvider):
    provider_type = 'gmail'
    requires_oauth = True

    def __init__(
        self,
        oauth_client: GmailOAuthClient,
        pubsub_project_id: str,
        pubsub_topic_prefix: str = 'agentic-trigger',
        push_endpoint_template: Optional[str] = None,
        oidc_service_account_email: Optional[str] = None,
    ):
        self._oauth = oauth_client
        self._pubsub_project_id = pubsub_project_id
        self._pubsub_topic_prefix = pubsub_topic_prefix
        self._push_endpoint_template = push_endpoint_template
        self._oidc_service_account_email = (
            oidc_service_account_email.strip() if oidc_service_account_email else None
        ) or None
        self._publisher_client: Optional[pubsub_v1.PublisherClient] = None
        self._subscriber_client: Optional[pubsub_v1.SubscriberClient] = None

    def _publisher(self) -> pubsub_v1.PublisherClient:
        if self._publisher_client is None:
            self._publisher_client = pubsub_v1.PublisherClient()
        return self._publisher_client

    def _subscriber(self) -> pubsub_v1.SubscriberClient:
        if self._subscriber_client is None:
            self._subscriber_client = pubsub_v1.SubscriberClient()
        return self._subscriber_client

    # ---- OAuth ----------------------------------------------------------

    def build_consent_url(
        self, trigger_id: str, scopes: Optional[List[str]] = None
    ) -> str:
        return self._oauth.build_consent_url(
            state=trigger_id, scopes=scopes or DEFAULT_GMAIL_SCOPES
        )

    async def exchange_oauth_code(self, code: str, trigger_id: str) -> TokenBundle:
        return await asyncio.to_thread(self._oauth.exchange_code, code)

    async def refresh_access_token(self, refresh_token: str) -> TokenBundle:
        return await asyncio.to_thread(self._oauth.refresh_access_token, refresh_token)

    # ---- Subscription lifecycle ----------------------------------------

    def _topic_name(self, trigger_id: str) -> str:
        return f'{self._pubsub_topic_prefix}-{trigger_id}'

    def _topic_path(self, trigger_id: str) -> str:
        return (
            f'projects/{self._pubsub_project_id}/topics/{self._topic_name(trigger_id)}'
        )

    def _subscription_path(self, trigger_id: str) -> str:
        sub_name = f'{self._pubsub_topic_prefix}-sub-{trigger_id}'
        return f'projects/{self._pubsub_project_id}/subscriptions/{sub_name}'

    def _push_endpoint(self, trigger_id: str, agentic_id: str) -> Optional[str]:
        if not self._push_endpoint_template:
            return None
        return self._push_endpoint_template.format(
            trigger_id=trigger_id, agentic_id=agentic_id
        )

    async def start_subscription(
        self,
        trigger_id: str,
        access_token: str,
        external_account_id: str,
        agentic_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        topic_path = self._topic_path(trigger_id)
        subscription_path = self._subscription_path(trigger_id)
        push_endpoint = (
            self._push_endpoint(trigger_id, agentic_id) if agentic_id else None
        )

        await asyncio.to_thread(
            self._ensure_topic_and_subscription,
            topic_path,
            subscription_path,
            push_endpoint,
        )

        history_id, watch_expiration = await asyncio.to_thread(
            self._call_users_watch,
            access_token,
            external_account_id,
            topic_path,
        )

        return {
            'email_address': external_account_id,
            'pubsub_topic': topic_path,
            'pubsub_subscription': subscription_path,
            'push_endpoint': push_endpoint,
            'oidc_audience': push_endpoint
            if self._oidc_service_account_email
            else None,
            'history_id': history_id,
            'watch_expiration': watch_expiration.isoformat()
            if watch_expiration
            else None,
        }

    async def stop_subscription(
        self,
        provider_config: Dict[str, Any],
        access_token: str,
        external_account_id: str,
    ) -> None:
        await asyncio.to_thread(
            self._call_users_stop, access_token, external_account_id
        )

        topic_path = provider_config.get('pubsub_topic')
        subscription_path = provider_config.get('pubsub_subscription')
        if subscription_path:
            await asyncio.to_thread(self._delete_subscription, subscription_path)
        if topic_path:
            await asyncio.to_thread(self._delete_topic, topic_path)

    async def renew_subscription(
        self,
        provider_config: Dict[str, Any],
        access_token: str,
        external_account_id: str,
    ) -> Dict[str, Any]:
        topic_path = provider_config['pubsub_topic']
        history_id, watch_expiration = await asyncio.to_thread(
            self._call_users_watch,
            access_token,
            external_account_id,
            topic_path,
        )
        updated = dict(provider_config)
        updated['history_id'] = history_id
        updated['watch_expiration'] = (
            watch_expiration.isoformat() if watch_expiration else None
        )
        return updated

    # ---- Event fetch / normalize ---------------------------------------

    def extract_push_cursor(self, raw_push_payload):
        try:
            _, history_id = self._decode_push_payload(raw_push_payload)
            return history_id
        except Exception:
            return None

    async def fetch_events(
        self,
        access_token: str,
        provider_config: Dict[str, Any],
        raw_push_payload: Dict[str, Any],
    ) -> List[NormalizedEmailEvent]:
        email_address, push_history_id = self._decode_push_payload(raw_push_payload)
        if email_address != provider_config.get('email_address'):
            logger.warning(
                f'Pub/Sub push email {email_address!r} does not match trigger '
                f'config {provider_config.get("email_address")!r}; ignoring'
            )
            return []

        start_history_id = int(provider_config.get('history_id') or push_history_id)
        return await asyncio.to_thread(
            self._fetch_and_normalize_messages,
            access_token,
            email_address,
            start_history_id,
        )

    # ---- Internals: Pub/Sub --------------------------------------------

    def _ensure_topic_and_subscription(
        self,
        topic_path: str,
        subscription_path: str,
        push_endpoint: Optional[str],
    ) -> None:
        publisher = self._publisher()

        # Create-or-ignore beats get-then-create: one round-trip in the steady
        # state, and avoids gRPC retries on NotFound.
        try:
            publisher.create_topic(request={'name': topic_path}, timeout=30)
        except google_exceptions.AlreadyExists:
            pass

        gmail_service_account = 'gmail-api-push@system.gserviceaccount.com'
        wants_role = 'roles/pubsub.publisher'
        wants_member = f'serviceAccount:{gmail_service_account}'
        try:
            policy = publisher.get_iam_policy(
                request={'resource': topic_path}, timeout=30
            )
            binding = next((b for b in policy.bindings if b.role == wants_role), None)
            mutated = False
            if binding is None:
                policy.bindings.add(role=wants_role, members=[wants_member])
                mutated = True
            elif wants_member not in binding.members:
                binding.members.append(wants_member)
                mutated = True
            if mutated:
                publisher.set_iam_policy(
                    request={'resource': topic_path, 'policy': policy},
                    timeout=30,
                )
        except Exception as exc:
            logger.warning(f'Could not set IAM policy on {topic_path}: {exc}')

        subscriber = self._subscriber()
        request: Dict[str, Any] = {
            'name': subscription_path,
            'topic': topic_path,
            'ack_deadline_seconds': 60,
            'message_retention_duration': {'seconds': 86400},
            'retry_policy': pubsub_v1.types.RetryPolicy(
                minimum_backoff={'seconds': 10},
                maximum_backoff={'seconds': 600},
            ),
        }
        if push_endpoint:
            push_config_kwargs: Dict[str, Any] = {'push_endpoint': push_endpoint}
            if self._oidc_service_account_email:
                push_config_kwargs['oidc_token'] = pubsub_v1.types.PushConfig.OidcToken(
                    service_account_email=self._oidc_service_account_email,
                    audience=push_endpoint,
                )
            request['push_config'] = pubsub_v1.types.PushConfig(**push_config_kwargs)
        try:
            subscriber.create_subscription(request=request, timeout=30)
        except google_exceptions.AlreadyExists:
            pass

    def _delete_subscription(self, subscription_path: str) -> None:
        try:
            self._subscriber().delete_subscription(
                request={'subscription': subscription_path}, timeout=30
            )
        except Exception as exc:
            logger.warning(f'Failed to delete subscription {subscription_path}: {exc}')

    def _delete_topic(self, topic_path: str) -> None:
        try:
            self._publisher().delete_topic(request={'topic': topic_path}, timeout=30)
        except Exception as exc:
            logger.warning(f'Failed to delete topic {topic_path}: {exc}')

    # ---- Internals: Gmail API ------------------------------------------

    def _gmail_service(self, access_token: str):
        credentials = Credentials(token=access_token)
        return build('gmail', 'v1', credentials=credentials, cache_discovery=False)

    def _call_users_watch(
        self,
        access_token: str,
        email_address: str,
        topic_path: str,
    ) -> Tuple[int, Optional[datetime]]:
        service = self._gmail_service(access_token)
        body = {
            'topicName': topic_path,
            'labelIds': ['INBOX'],
            'labelFilterAction': 'include',
        }
        response = service.users().watch(userId=email_address, body=body).execute()
        history_id = int(response['historyId'])
        expiration_ms = response.get('expiration')
        expiration = (
            datetime.fromtimestamp(int(expiration_ms) / 1000, tz=timezone.utc)
            if expiration_ms
            else datetime.now(timezone.utc) + timedelta(days=7)
        )
        return history_id, expiration

    def _call_users_stop(self, access_token: str, email_address: str) -> None:
        service = self._gmail_service(access_token)
        try:
            service.users().stop(userId=email_address).execute()
        except Exception as exc:
            logger.warning(f'users.stop for {email_address} failed: {exc}')

    def _decode_push_payload(self, raw_push_payload: Dict[str, Any]) -> Tuple[str, int]:
        message = raw_push_payload.get('message') or {}
        data_b64 = message.get('data')
        if not data_b64:
            raise ValueError('Pub/Sub push has no message.data')
        decoded = json.loads(base64.b64decode(data_b64).decode('utf-8'))
        return decoded['emailAddress'], int(decoded['historyId'])

    def _fetch_and_normalize_messages(
        self,
        access_token: str,
        email_address: str,
        start_history_id: int,
    ) -> List[NormalizedEmailEvent]:
        service = self._gmail_service(access_token)
        message_ids = self._list_new_message_ids(
            service, email_address, start_history_id
        )

        events: List[NormalizedEmailEvent] = []
        for message_id in message_ids:
            try:
                events.append(
                    self._fetch_single_message(service, email_address, message_id)
                )
            except Exception as exc:
                logger.warning(f'Failed to fetch Gmail message {message_id}: {exc}')

        return events

    def _list_new_message_ids(
        self, service, email_address: str, start_history_id: int
    ) -> List[str]:
        message_ids: List[str] = []
        page_token: Optional[str] = None
        while True:
            request_kwargs: Dict[str, Any] = {
                'userId': email_address,
                'startHistoryId': str(start_history_id),
                'historyTypes': ['messageAdded'],
                'labelId': 'INBOX',
            }
            if page_token:
                request_kwargs['pageToken'] = page_token
            response = service.users().history().list(**request_kwargs).execute()

            for history_entry in response.get('history', []):
                for added in history_entry.get('messagesAdded', []):
                    msg = added.get('message') or {}
                    msg_id = msg.get('id')
                    if msg_id and msg_id not in message_ids:
                        message_ids.append(msg_id)

            page_token = response.get('nextPageToken')
            if not page_token:
                break

        return message_ids

    def _fetch_single_message(
        self, service, email_address: str, message_id: str
    ) -> NormalizedEmailEvent:
        msg = (
            service.users()
            .messages()
            .get(userId=email_address, id=message_id, format='full')
            .execute()
        )
        headers = {
            h['name'].lower(): h['value']
            for h in msg.get('payload', {}).get('headers', [])
        }
        subject = headers.get('subject', '')
        sender = headers.get('from')

        body_text, attachments_meta = self._walk_parts(msg.get('payload', {}))
        attachments = [
            Attachment(
                file_name=meta['filename'],
                mime_type=meta['mime_type'],
                content_bytes=self._download_attachment(
                    service, email_address, message_id, meta['attachment_id']
                ),
            )
            for meta in attachments_meta
        ]

        return NormalizedEmailEvent(
            provider_event_id=message_id,
            subject=subject,
            sender=sender,
            body_text=body_text,
            attachments=attachments,
        )

    def _walk_parts(self, payload: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
        text_parts: List[str] = []
        html_parts: List[str] = []
        attachments: List[Dict[str, Any]] = []

        def _walk(part: Dict[str, Any]) -> None:
            mime_type = part.get('mimeType', '')
            filename = part.get('filename') or ''
            body = part.get('body') or {}

            if part.get('parts'):
                for child in part['parts']:
                    _walk(child)
                return

            if filename and body.get('attachmentId'):
                attachments.append(
                    {
                        'filename': filename,
                        'mime_type': mime_type,
                        'attachment_id': body['attachmentId'],
                    }
                )
                return

            data_b64 = body.get('data')
            if not data_b64:
                return
            decoded = base64.urlsafe_b64decode(data_b64.encode('utf-8'))
            try:
                text = decoded.decode('utf-8', errors='replace')
            except Exception:
                return

            if mime_type == 'text/plain':
                text_parts.append(text)
            elif mime_type == 'text/html':
                html_parts.append(text)

        _walk(payload)

        if text_parts:
            return '\n'.join(text_parts).strip(), attachments
        if html_parts:
            soup = BeautifulSoup('\n'.join(html_parts), 'html.parser')
            return soup.get_text(separator='\n').strip(), attachments
        return '', attachments

    def _download_attachment(
        self, service, email_address: str, message_id: str, attachment_id: str
    ) -> bytes:
        response = (
            service.users()
            .messages()
            .attachments()
            .get(userId=email_address, messageId=message_id, id=attachment_id)
            .execute()
        )
        data_b64 = response.get('data') or ''
        return base64.urlsafe_b64decode(data_b64.encode('utf-8'))
