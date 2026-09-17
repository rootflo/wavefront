import asyncio
import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlencode

import requests

from ..helper import build_graph_message, capabilities_from_scopes, resolve_scopes
from ..types import (
    Attachment,
    EmailCapability,
    EmailProviderABC,
    EmailProviderError,
    EmailProviderType,
    NormalizedEmail,
    OutboundMessage,
    TokenBundle,
)
from .config import OutlookAppConfig

logger = logging.getLogger(__name__)

GRAPH_BASE_URL = 'https://graph.microsoft.com/v1.0'

SCOPE_CATALOG = {
    EmailCapability.READ: ['https://graph.microsoft.com/Mail.Read'],
    EmailCapability.SEND: ['https://graph.microsoft.com/Mail.Send'],
    EmailCapability.MODIFY: ['https://graph.microsoft.com/Mail.ReadWrite'],
}

# `offline_access` is what makes the refresh token appear; `User.Read` resolves
# which mailbox consented.
IDENTITY_SCOPES = [
    'offline_access',
    'openid',
    'https://graph.microsoft.com/User.Read',
]


class OutlookProvider(EmailProviderABC):
    """Delegated Microsoft Graph access to a connected mailbox.

    Unlike the previous app-only integration, every call acts as the user who
    consented, so sending is not restricted to one configured sender.

    Graph change notifications are not implemented: subscriptions there are
    short-lived and need a validation handshake on the push endpoint, so inbox
    watch stays Gmail-only until that is built.
    """

    provider_type = EmailProviderType.OUTLOOK

    def __init__(self, config: OutlookAppConfig):
        self.config = config

    # ---- Scopes ---------------------------------------------------------

    def scopes_for(self, capabilities: Sequence[EmailCapability]) -> List[str]:
        return resolve_scopes(SCOPE_CATALOG, capabilities, IDENTITY_SCOPES)

    def capabilities_for(self, granted_scopes: Optional[str]) -> List[EmailCapability]:
        return capabilities_from_scopes(SCOPE_CATALOG, granted_scopes)

    # ---- OAuth ----------------------------------------------------------

    def build_consent_url(self, state: str, scopes: Sequence[str]) -> str:
        params = {
            'client_id': self.config.client_id,
            'response_type': 'code',
            'redirect_uri': self.config.redirect_uri,
            'response_mode': 'query',
            'scope': ' '.join(scopes),
            'prompt': 'consent',
            'state': state,
        }
        return f'{self.config.authority}/oauth2/v2.0/authorize?{urlencode(params)}'

    async def exchange_code(self, code: str) -> TokenBundle:
        return await asyncio.to_thread(self._exchange_code_sync, code)

    def _exchange_code_sync(self, code: str) -> TokenBundle:
        payload = self._token_request(
            {
                'code': code,
                'redirect_uri': self.config.redirect_uri,
                'grant_type': 'authorization_code',
            }
        )

        refresh_token = payload.get('refresh_token')
        if not refresh_token:
            raise EmailProviderError(
                'Microsoft did not return a refresh_token. Ensure the consent '
                'URL requests the offline_access scope.'
            )
        access_token = payload.get('access_token')
        email = self._fetch_user_email(access_token) if access_token else None
        if not email:
            raise EmailProviderError('Failed to resolve Microsoft account email.')

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
        payload = self._token_request(
            {
                'refresh_token': refresh_token,
                'grant_type': 'refresh_token',
            }
        )
        # Microsoft rotates refresh tokens, so keep whichever one came back.
        return TokenBundle(
            refresh_token=payload.get('refresh_token') or refresh_token,
            access_token=payload['access_token'],
            expires_at=self._expires_at(payload.get('expires_in')),
            scopes=payload.get('scope'),
            external_account_id='',
        )

    def _token_request(self, extra: Dict[str, str]) -> Dict[str, Any]:
        data = {
            'client_id': self.config.client_id,
            'client_secret': self.config.client_secret,
            **extra,
        }
        response = requests.post(
            f'{self.config.authority}/oauth2/v2.0/token', data=data, timeout=20
        )
        if not response.ok:
            logger.error(
                'Microsoft token request failed: status=%s body=%s',
                response.status_code,
                response.text,
            )
            response.raise_for_status()
        return response.json()

    async def get_account_email(self, access_token: str) -> Optional[str]:
        return await asyncio.to_thread(self._fetch_user_email, access_token)

    def _fetch_user_email(self, access_token: str) -> Optional[str]:
        response = requests.get(
            f'{GRAPH_BASE_URL}/me',
            headers=self._headers(access_token),
            timeout=20,
        )
        response.raise_for_status()
        profile = response.json()
        return profile.get('mail') or profile.get('userPrincipalName')

    @staticmethod
    def _expires_at(expires_in: Any) -> Optional[datetime]:
        if not expires_in:
            return None
        return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    @staticmethod
    def _headers(access_token: str) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }

    # ---- Mailbox operations ---------------------------------------------

    async def send_message(
        self,
        access_token: str,
        mailbox: str,
        message: OutboundMessage,
    ) -> Optional[str]:
        return await asyncio.to_thread(self._send_message_sync, access_token, message)

    def _send_message_sync(
        self, access_token: str, message: OutboundMessage
    ) -> Optional[str]:
        response = requests.post(
            f'{GRAPH_BASE_URL}/me/sendMail',
            headers=self._headers(access_token),
            json={'message': build_graph_message(message)},
            timeout=30,
        )
        if response.status_code != 202:
            raise EmailProviderError(
                f'Graph sendMail failed: status={response.status_code} '
                f'body={response.text}'
            )
        # sendMail returns 202 with an empty body; there is no id to report.
        return None

    async def get_message(
        self,
        access_token: str,
        mailbox: str,
        message_id: str,
    ) -> NormalizedEmail:
        return await asyncio.to_thread(self._get_message_sync, access_token, message_id)

    def _get_message_sync(self, access_token: str, message_id: str) -> NormalizedEmail:
        response = requests.get(
            f'{GRAPH_BASE_URL}/me/messages/{message_id}',
            headers=self._headers(access_token),
            params={'$select': 'subject,from,body,bodyPreview,hasAttachments'},
            timeout=30,
        )
        response.raise_for_status()
        msg = response.json()

        body = msg.get('body') or {}
        content = body.get('content') or ''
        if (body.get('contentType') or '').lower() == 'html':
            from ..helper import html_to_text

            body_text = html_to_text(content)
        else:
            body_text = content.strip()

        sender = ((msg.get('from') or {}).get('emailAddress') or {}).get('address')
        attachments = (
            self._fetch_attachments(access_token, message_id)
            if msg.get('hasAttachments')
            else []
        )

        return NormalizedEmail(
            provider_event_id=message_id,
            subject=msg.get('subject') or '',
            sender=sender,
            body_text=body_text,
            attachments=attachments,
        )

    def _fetch_attachments(
        self, access_token: str, message_id: str
    ) -> List[Attachment]:
        response = requests.get(
            f'{GRAPH_BASE_URL}/me/messages/{message_id}/attachments',
            headers=self._headers(access_token),
            timeout=30,
        )
        response.raise_for_status()
        attachments: List[Attachment] = []
        for item in response.json().get('value', []):
            content_bytes = item.get('contentBytes')
            if not content_bytes:
                # Item attachments (forwarded mail, events) carry no raw bytes.
                continue
            attachments.append(
                Attachment(
                    file_name=item.get('name') or 'attachment',
                    mime_type=item.get('contentType') or 'application/octet-stream',
                    content_bytes=base64.b64decode(content_bytes),
                )
            )
        return attachments

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
        raise EmailProviderError(
            'Inbox watch is not implemented for Outlook connections yet.'
        )

    async def renew_watch(
        self,
        access_token: str,
        mailbox: str,
        provider_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        raise EmailProviderError(
            'Inbox watch is not implemented for Outlook connections yet.'
        )

    async def stop_watch(
        self,
        access_token: str,
        mailbox: str,
        provider_config: Dict[str, Any],
    ) -> None:
        return None

    async def fetch_events(
        self,
        access_token: str,
        provider_config: Dict[str, Any],
        raw_push_payload: Dict[str, Any],
    ) -> List[NormalizedEmail]:
        return []
