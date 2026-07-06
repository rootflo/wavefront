from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import urlencode

import requests

from common_module.log.logger import logger
from triggers_module.providers.base import TokenBundle


GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v2/userinfo'


class GmailOAuthClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def build_consent_url(self, state: str, scopes: List[str]) -> str:
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(scopes),
            'access_type': 'offline',
            'prompt': 'consent',
            # 'include_granted_scopes': 'true',
            'state': state,
        }
        return f'{GOOGLE_AUTH_URL}?{urlencode(params)}'

    def exchange_code(self, code: str) -> TokenBundle:
        response = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                'code': code,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'redirect_uri': self.redirect_uri,
                'grant_type': 'authorization_code',
            },
            timeout=20,
        )
        if not response.ok:
            logger.error(
                f'Google token exchange failed: status={response.status_code} '
                f'body={response.text} redirect_uri={self.redirect_uri!r}'
            )
            response.raise_for_status()
        payload = response.json()

        refresh_token = payload.get('refresh_token')
        if not refresh_token:
            raise RuntimeError(
                'Google did not return a refresh_token. Ensure the consent URL '
                'requests access_type=offline and prompt=consent.'
            )
        access_token = payload.get('access_token')
        expires_in = payload.get('expires_in')
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
            if expires_in
            else None
        )

        email = self._fetch_user_email(access_token) if access_token else None
        if not email:
            raise RuntimeError('Failed to resolve Google account email.')

        return TokenBundle(
            refresh_token=refresh_token,
            access_token=access_token,
            expires_at=expires_at,
            scopes=payload.get('scope'),
            external_account_id=email,
        )

    def refresh_access_token(self, refresh_token: str) -> TokenBundle:
        response = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                'refresh_token': refresh_token,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'refresh_token',
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        access_token = payload['access_token']
        expires_in = payload.get('expires_in')
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
            if expires_in
            else None
        )
        return TokenBundle(
            refresh_token=refresh_token,
            access_token=access_token,
            expires_at=expires_at,
            scopes=payload.get('scope'),
            external_account_id='',
        )

    def _fetch_user_email(self, access_token: str) -> Optional[str]:
        response = requests.get(
            GOOGLE_USERINFO_URL,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=20,
        )
        response.raise_for_status()
        return response.json().get('email')
