import asyncio
import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
from google.api_core import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.cloud import pubsub_v1
from google.oauth2 import id_token
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from ..helper import capabilities_from_scopes, encode_raw_message, resolve_scopes
from ..types import (
    Attachment,
    EmailCapability,
    EmailProviderABC,
    EmailProviderError,
    EmailProviderType,
    NormalizedEmail,
    OutboundMessage,
    PushSignatureError,
    TokenBundle,
)
from .config import GmailAppConfig, GmailWatchConfig

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v2/userinfo'

# Gmail publishes watch notifications through this fixed service account.
GMAIL_PUSH_SERVICE_ACCOUNT = 'gmail-api-push@system.gserviceaccount.com'

SCOPE_CATALOG = {
    EmailCapability.READ: ['https://www.googleapis.com/auth/gmail.readonly'],
    EmailCapability.SEND: ['https://www.googleapis.com/auth/gmail.send'],
    EmailCapability.MODIFY: ['https://www.googleapis.com/auth/gmail.modify'],
}

# Resolving which mailbox consented is what turns a token into a connection.
IDENTITY_SCOPES = ['https://www.googleapis.com/auth/userinfo.email']


class GmailProvider(EmailProviderABC):
    provider_type = EmailProviderType.GMAIL

    def __init__(self, config: GmailAppConfig):
        self.config = config
        self._publisher_client: Optional[pubsub_v1.PublisherClient] = None
        self._subscriber_client: Optional[pubsub_v1.SubscriberClient] = None
        self._id_token_request = None

    # ---- Scopes ---------------------------------------------------------

    def scopes_for(self, capabilities: Sequence[EmailCapability]) -> List[str]:
        return resolve_scopes(SCOPE_CATALOG, capabilities, IDENTITY_SCOPES)

    def capabilities_for(self, granted_scopes: Optional[str]) -> List[EmailCapability]:
        return capabilities_from_scopes(SCOPE_CATALOG, granted_scopes)

    # ---- OAuth ----------------------------------------------------------

    def build_consent_url(self, state: str, scopes: Sequence[str]) -> str:
        params = {
            'client_id': self.config.client_id,
            'redirect_uri': self.config.redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(scopes),
            'access_type': 'offline',
            # Forced so a scope upgrade still returns a refresh token: Google
            # only issues one on explicit consent, and losing it would strand
            # the connection.
            'prompt': 'consent',
            'include_granted_scopes': 'true',
            'state': state,
        }
        return f'{GOOGLE_AUTH_URL}?{urlencode(params)}'

    async def exchange_code(self, code: str) -> TokenBundle:
        return await asyncio.to_thread(self._exchange_code_sync, code)

    def _exchange_code_sync(self, code: str) -> TokenBundle:
        response = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                'code': code,
                'client_id': self.config.client_id,
                'client_secret': self.config.client_secret,
                'redirect_uri': self.config.redirect_uri,
                'grant_type': 'authorization_code',
            },
            timeout=20,
        )
        if not response.ok:
            logger.error(
                'Google token exchange failed: status=%s body=%s redirect_uri=%r',
                response.status_code,
                response.text,
                self.config.redirect_uri,
            )
            response.raise_for_status()
        payload = response.json()

        refresh_token = payload.get('refresh_token')
        if not refresh_token:
            raise EmailProviderError(
                'Google did not return a refresh_token. Ensure the consent URL '
                'requests access_type=offline and prompt=consent.'
            )
        access_token = payload.get('access_token')
        email = self._fetch_user_email(access_token) if access_token else None
        if not email:
            raise EmailProviderError('Failed to resolve Google account email.')

        return TokenBundle(
            refresh_token=refresh_token,
            access_token=access_token,
            expires_at=self._expires_at(payload.get('expires_in')),
            scopes=payload.get('scope'),
            external_account_id=email,
        )

    async def refresh_access_token(self, refresh_token: str) -> TokenBundle:
        return await asyncio.to_thread(self._refresh_access_token_sync, refresh_token)

    def _refresh_access_token_sync(self, refresh_token: str) -> TokenBundle:
        response = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                'refresh_token': refresh_token,
                'client_id': self.config.client_id,
                'client_secret': self.config.client_secret,
                'grant_type': 'refresh_token',
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        return TokenBundle(
            refresh_token=refresh_token,
            access_token=payload['access_token'],
            expires_at=self._expires_at(payload.get('expires_in')),
            scopes=payload.get('scope'),
            external_account_id='',
        )

    async def get_account_email(self, access_token: str) -> Optional[str]:
        return await asyncio.to_thread(self._fetch_user_email, access_token)

    def _fetch_user_email(self, access_token: str) -> Optional[str]:
        response = requests.get(
            GOOGLE_USERINFO_URL,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=20,
        )
        response.raise_for_status()
        return response.json().get('email')

    @staticmethod
    def _expires_at(expires_in: Any) -> Optional[datetime]:
        if not expires_in:
            return None
        return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    # ---- Mailbox operations ---------------------------------------------

    async def send_message(
        self,
        access_token: str,
        mailbox: str,
        message: OutboundMessage,
    ) -> Optional[str]:
        return await asyncio.to_thread(
            self._send_message_sync, access_token, mailbox, message
        )

    def _send_message_sync(
        self, access_token: str, mailbox: str, message: OutboundMessage
    ) -> Optional[str]:
        service = self._gmail_service(access_token)
        raw = encode_raw_message(mailbox, message)
        sent = service.users().messages().send(userId='me', body={'raw': raw}).execute()
        message_id = sent.get('id')
        logger.info('Gmail message sent successfully: %s', message_id)
        return message_id

    async def get_message(
        self,
        access_token: str,
        mailbox: str,
        message_id: str,
    ) -> NormalizedEmail:
        service = await asyncio.to_thread(self._gmail_service, access_token)
        return await asyncio.to_thread(
            self._fetch_single_message, service, mailbox, message_id
        )

    # ---- Watch subscriptions --------------------------------------------

    async def start_watch(
        self,
        access_token: str,
        mailbox: str,
        watch_key: str,
        *,
        watch_config: Optional[Any] = None,
        push_endpoint_params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        if not isinstance(watch_config, GmailWatchConfig):
            raise EmailProviderError(
                'Gmail inbox watch requires a GmailWatchConfig from the '
                'triggers runtime; it is not part of the OAuth app.'
            )

        topic_path = watch_config.topic_path(watch_key)
        subscription_path = watch_config.subscription_path(watch_key)
        push_endpoint = watch_config.push_endpoint(push_endpoint_params or {})

        await asyncio.to_thread(
            self._ensure_topic_and_subscription,
            watch_config,
            topic_path,
            subscription_path,
            push_endpoint,
        )

        history_id, watch_expiration = await asyncio.to_thread(
            self._call_users_watch, access_token, mailbox, topic_path
        )

        return {
            'email_address': mailbox,
            'pubsub_topic': topic_path,
            'pubsub_subscription': subscription_path,
            'push_endpoint': push_endpoint,
            'oidc_audience': push_endpoint
            if watch_config.oidc_service_account_email
            else None,
            'history_id': history_id,
            'watch_expiration': watch_expiration.isoformat()
            if watch_expiration
            else None,
        }

    async def renew_watch(
        self,
        access_token: str,
        mailbox: str,
        provider_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        topic_path = provider_config['pubsub_topic']
        history_id, watch_expiration = await asyncio.to_thread(
            self._call_users_watch, access_token, mailbox, topic_path
        )
        updated = dict(provider_config)
        updated['history_id'] = history_id
        updated['watch_expiration'] = (
            watch_expiration.isoformat() if watch_expiration else None
        )
        return updated

    async def stop_watch(
        self,
        access_token: str,
        mailbox: str,
        provider_config: Dict[str, Any],
    ) -> None:
        await asyncio.to_thread(self._call_users_stop, access_token, mailbox)

        subscription_path = provider_config.get('pubsub_subscription')
        topic_path = provider_config.get('pubsub_topic')
        if subscription_path:
            await asyncio.to_thread(self._delete_subscription, subscription_path)
        if topic_path:
            await asyncio.to_thread(self._delete_topic, topic_path)

    # ---- Push handling ---------------------------------------------------

    def verify_push(
        self,
        authorization_header: Optional[str],
        expected_audience: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verify the OIDC JWT Pub/Sub attaches to push requests.

        Pub/Sub only signs pushes when the subscription was created with an
        `oidc_token` PushConfig, so callers skip this unless the stored config
        records that OIDC was configured.
        """
        if not authorization_header or not authorization_header.lower().startswith(
            'bearer '
        ):
            raise PushSignatureError(
                'Missing or malformed Authorization header on Pub/Sub push'
            )

        token = authorization_header.split(' ', 1)[1].strip()
        try:
            claims = id_token.verify_oauth2_token(
                token,
                self._id_token_verifier(),
                audience=expected_audience,
            )
        except Exception as exc:
            logger.warning('Pub/Sub push signature verification failed: %s', exc)
            raise PushSignatureError(str(exc)) from exc

        issuer = claims.get('iss')
        if issuer not in ('https://accounts.google.com', 'accounts.google.com'):
            raise PushSignatureError(f'Unexpected JWT issuer: {issuer}')

        return claims

    def extract_push_cursor(self, raw_push_payload: Dict[str, Any]) -> Optional[int]:
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
    ) -> List[NormalizedEmail]:
        email_address, push_history_id = self._decode_push_payload(raw_push_payload)
        if email_address != provider_config.get('email_address'):
            logger.warning(
                'Pub/Sub push email %r does not match watch config %r; ignoring',
                email_address,
                provider_config.get('email_address'),
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

    def _publisher(self) -> pubsub_v1.PublisherClient:
        if self._publisher_client is None:
            self._publisher_client = pubsub_v1.PublisherClient()
        return self._publisher_client

    def _subscriber(self) -> pubsub_v1.SubscriberClient:
        if self._subscriber_client is None:
            self._subscriber_client = pubsub_v1.SubscriberClient()
        return self._subscriber_client

    def _id_token_verifier(self):
        if self._id_token_request is None:
            self._id_token_request = google_requests.Request()
        return self._id_token_request

    def _ensure_topic_and_subscription(
        self,
        watch_config: GmailWatchConfig,
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

        wants_role = 'roles/pubsub.publisher'
        wants_member = f'serviceAccount:{GMAIL_PUSH_SERVICE_ACCOUNT}'
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
        except google_exceptions.PermissionDenied as exc:
            logger.error(
                'Permission denied setting IAM policy on %s (role=%s, member=%s). '
                'Gmail will not be able to publish to this topic: %s',
                topic_path,
                wants_role,
                wants_member,
                exc,
            )
            raise
        except google_exceptions.GoogleAPIError as exc:
            logger.error(
                'Failed to set IAM policy on %s (role=%s, member=%s): %s',
                topic_path,
                wants_role,
                wants_member,
                exc,
            )
            raise

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
            if watch_config.oidc_service_account_email:
                push_config_kwargs['oidc_token'] = pubsub_v1.types.PushConfig.OidcToken(
                    service_account_email=watch_config.oidc_service_account_email,
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
            logger.warning(
                'Failed to delete subscription %s: %s', subscription_path, exc
            )

    def _delete_topic(self, topic_path: str) -> None:
        try:
            self._publisher().delete_topic(request={'topic': topic_path}, timeout=30)
        except Exception as exc:
            logger.warning('Failed to delete topic %s: %s', topic_path, exc)

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
            logger.warning('users.stop for %s failed: %s', email_address, exc)

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
    ) -> List[NormalizedEmail]:
        service = self._gmail_service(access_token)
        message_ids = self._list_new_message_ids(
            service, email_address, start_history_id
        )

        events: List[NormalizedEmail] = []
        for message_id in message_ids:
            try:
                events.append(
                    self._fetch_single_message(service, email_address, message_id)
                )
            except Exception as exc:
                logger.warning('Failed to fetch Gmail message %s: %s', message_id, exc)

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
    ) -> NormalizedEmail:
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

        return NormalizedEmail(
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
