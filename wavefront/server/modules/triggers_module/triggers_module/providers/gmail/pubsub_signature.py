from typing import Optional

from common_module.log.logger import logger
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token


class PubSubSignatureError(Exception):
    pass


class PubSubPushVerifier:
    """Verifies the OIDC JWT that Google Pub/Sub attaches to push requests.

    Pub/Sub only signs pushes when the subscription is created with an
    `oidc_token` PushConfig. If a subscription was created without that, no
    Authorization header is sent and this verifier should be skipped at the
    caller (TriggerPushReceiver only calls verify when the trigger's
    provider_config records that OIDC was configured).
    """

    def __init__(self):
        self._request = google_requests.Request()

    def verify(
        self,
        authorization_header: Optional[str],
        expected_audience: Optional[str] = None,
    ) -> dict:
        if not authorization_header or not authorization_header.lower().startswith(
            'bearer '
        ):
            raise PubSubSignatureError(
                'Missing or malformed Authorization header on Pub/Sub push'
            )

        token = authorization_header.split(' ', 1)[1].strip()
        try:
            claims = id_token.verify_oauth2_token(
                token,
                self._request,
                audience=expected_audience,
            )
        except Exception as exc:
            logger.warning(f'Pub/Sub push signature verification failed: {exc}')
            raise PubSubSignatureError(str(exc)) from exc

        issuer = claims.get('iss')
        if issuer not in ('https://accounts.google.com', 'accounts.google.com'):
            raise PubSubSignatureError(f'Unexpected JWT issuer: {issuer}')

        return claims
