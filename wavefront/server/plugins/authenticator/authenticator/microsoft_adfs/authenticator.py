import json
import logging
import re
import ssl
import jwt
import requests
from datetime import datetime
from jwt import PyJWKClient
from typing import Dict, Any, Optional
from urllib.parse import urlencode, urlparse

from ..types import AuthenticatorABC, AuthResult, TokenResult, HealthStatus, UserInfo
from .config import MicrosoftADFSConfig

logger = logging.getLogger(__name__)

_ALLOWED_ID_TOKEN_ALGS = ['RS256', 'RS384', 'RS512', 'ES256', 'ES384', 'ES512']


class MicrosoftADFSAuthenticator(AuthenticatorABC):
    """Microsoft ADFS (OIDC) authenticator.

    Identity is sourced from the `id_token` returned in the token response
    rather than a userinfo / Graph call, since on-prem ADFS does not always
    expose `/adfs/userinfo` and Microsoft Graph is unreachable.
    """

    def __init__(self, config: MicrosoftADFSConfig):
        self.config = config
        base = config.authority.rstrip('/')
        self.auth_url = f'{base}{config.authorize_path}'
        self.token_url = f'{base}{config.token_path}'
        self.jwks_url = f'{base}{config.jwks_path}'

        ssl_ctx = ssl.create_default_context()
        if not config.verify_ssl:
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
        # PyJWKClient caches keys in-process; safe to construct once per instance.
        self._jwks_client = PyJWKClient(self.jwks_url, ssl_context=ssl_ctx)

    @staticmethod
    def validate_config_static(config: Dict[str, Any]) -> bool:
        required_fields = [
            'client_id',
            'client_secret',
            'authority',
            'redirect_uri',
            'client_redirect_success_url',
            'client_redirect_failure_url',
            'scopes',
        ]
        for field_name in required_fields:
            if not config.get(field_name):
                raise ValueError(f'{field_name} is required')

        authority = config['authority']
        if not authority.startswith('https://'):
            raise ValueError('authority must be a valid HTTPS URL')

        parsed_uri = urlparse(config['redirect_uri'])
        if not parsed_uri.scheme or not parsed_uri.netloc:
            raise ValueError('redirect_uri must be a valid URL with scheme and netloc')

        for url_field in ['client_redirect_success_url', 'client_redirect_failure_url']:
            parsed_url = urlparse(config[url_field])
            if not parsed_url.scheme or not parsed_url.netloc:
                raise ValueError(
                    f'{url_field} must be a valid URL with scheme and netloc'
                )

        scopes = config.get('scopes', [])
        if not scopes or len(scopes) == 0:
            raise ValueError('scopes array cannot be empty')

        return True

    def authenticate(
        self,
        credentials: Dict[str, Any],
        expected_nonce: Optional[str] = None,
    ) -> AuthResult:
        authorization_code = credentials.get('authorization_code')

        if not authorization_code:
            return AuthResult(
                success=False,
                error='Authorization code is required',
                error_code='MISSING_AUTH_CODE',
            )

        token_result, id_token = self._exchange_code_for_token(authorization_code)

        if not token_result.success:
            return AuthResult(
                success=False,
                error=token_result.error,
                error_code='TOKEN_EXCHANGE_FAILED',
            )

        if not id_token:
            return AuthResult(
                success=False,
                error='ADFS response missing id_token',
                error_code='ID_TOKEN_MISSING',
            )

        user_info = self._get_user_info_from_id_token(id_token, expected_nonce)

        if not user_info:
            return AuthResult(
                success=False,
                error='Failed to extract user information from id_token',
                error_code='USER_INFO_FAILED',
            )

        return AuthResult(
            success=True,
            user_info=user_info,
            access_token=token_result.access_token,
            refresh_token=token_result.refresh_token,
        )

    def validate_config(self) -> bool:
        try:
            required_fields = [
                'client_id',
                'client_secret',
                'authority',
                'redirect_uri',
                'client_redirect_success_url',
                'client_redirect_failure_url',
                'scopes',
            ]
            for field_name in required_fields:
                if not getattr(self.config, field_name, None):
                    return False

            if not self.config.authority.startswith('https://'):
                return False

            for url in (
                self.config.redirect_uri,
                self.config.client_redirect_success_url,
                self.config.client_redirect_failure_url,
            ):
                parsed = urlparse(url)
                if not parsed.scheme or not parsed.netloc:
                    return False

            if not self.config.scopes or len(self.config.scopes) == 0:
                return False

            return True

        except Exception:
            return False

    def get_authorization_url(
        self, state: Optional[str] = None, nonce: Optional[str] = None
    ) -> Optional[str]:
        if not state:
            raise ValueError("State doesn't exist Microsoft ADFS")

        params = {
            'response_type': self.config.response_type,
            'client_id': self.config.client_id,
            'redirect_uri': self.config.redirect_uri,
            'scope': ' '.join(self.config.scopes),
            'state': state,
            'response_mode': self.config.response_mode,
            'prompt': 'select_account',
        }

        if nonce:
            params['nonce'] = nonce

        url = f'{self.auth_url}?{urlencode(params)}'
        logger.debug(
            'ADFS authorize URL built (state_set=%s nonce_set=%s): %s',
            bool(state),
            bool(nonce),
            url,
        )
        return url

    def handle_callback(
        self, callback_data: Dict[str, Any], expected_nonce: Optional[str] = None
    ) -> AuthResult:
        logger.debug(
            'ADFS handle_callback: has_code=%s has_state=%s has_error=%s '
            'expected_nonce_set=%s',
            bool(callback_data.get('authorization_code')),
            bool(callback_data.get('state')),
            bool(callback_data.get('error')),
            expected_nonce is not None,
        )
        return self.authenticate(callback_data, expected_nonce=expected_nonce)

    def refresh_token(self, refresh_token: str) -> TokenResult:
        if not refresh_token:
            return TokenResult(success=False, error='Refresh token is required')

        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': self.config.client_id,
            'client_secret': self.config.client_secret,
            'scope': ' '.join(self.config.scopes),
        }

        try:
            response = requests.post(
                self.token_url,
                data=data,
                timeout=10,
                verify=self.config.verify_ssl,
            )
            response.raise_for_status()
            token_data = response.json()

            return TokenResult(
                success=True,
                access_token=token_data.get('access_token'),
                refresh_token=token_data.get('refresh_token', refresh_token),
                expires_in=token_data.get('expires_in'),
            )

        except requests.exceptions.RequestException as e:
            return TokenResult(success=False, error=f'Token refresh failed: {str(e)}')
        except json.JSONDecodeError:
            return TokenResult(
                success=False, error='Invalid response from ADFS token endpoint'
            )

    def logout(self, user_session: Dict[str, Any]) -> bool:
        return True

    def get_health_status(self) -> HealthStatus:
        is_healthy = True
        details = {
            'config_valid': self.validate_config(),
            'authority': self.config.authority,
            'scopes': self.config.scopes,
        }

        discovery_url = (
            f'{self.config.authority.rstrip("/")}/adfs/.well-known/openid-configuration'
        )
        try:
            response = requests.get(
                discovery_url, timeout=5, verify=self.config.verify_ssl
            )
            details['discovery_reachable'] = response.status_code == 200
            if response.status_code != 200:
                is_healthy = False
        except Exception:
            details['discovery_reachable'] = False
            is_healthy = False

        return HealthStatus(
            healthy=is_healthy,
            message='Microsoft ADFS authenticator is operational'
            if is_healthy
            else 'ADFS discovery endpoint unreachable',
            last_check=datetime.now(),
            details=details,
        )

    def get_user_info(self, access_token: str) -> Optional[UserInfo]:
        # ADFS access tokens are opaque without a guaranteed userinfo endpoint.
        # Identity is resolved from the id_token at login time instead.
        return None

    def _exchange_code_for_token(
        self, authorization_code: str
    ) -> tuple[TokenResult, Optional[str]]:
        data = {
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'client_id': self.config.client_id,
            'client_secret': self.config.client_secret,
            'redirect_uri': self.config.redirect_uri,
            'scope': ' '.join(self.config.scopes),
        }

        logger.debug('ADFS token exchange: POST %s', self.token_url)

        try:
            response = requests.post(
                self.token_url,
                data=data,
                timeout=10,
                verify=self.config.verify_ssl,
            )
            response.raise_for_status()
            token_data = response.json()

            id_token = token_data.get('id_token')
            logger.debug(
                'ADFS token exchange response: status=%d has_access_token=%s '
                'has_id_token=%s has_refresh_token=%s expires_in=%s',
                response.status_code,
                bool(token_data.get('access_token')),
                bool(id_token),
                bool(token_data.get('refresh_token')),
                token_data.get('expires_in'),
            )
            logger.debug('ADFS id_token=%s', id_token)

            return (
                TokenResult(
                    success=True,
                    access_token=token_data.get('access_token'),
                    refresh_token=token_data.get('refresh_token'),
                    expires_in=token_data.get('expires_in'),
                ),
                id_token,
            )

        except requests.exceptions.RequestException as e:
            logger.debug('ADFS token exchange request failed: %s', e)
            return (
                TokenResult(success=False, error=f'Token exchange failed: {str(e)}'),
                None,
            )
        except json.JSONDecodeError as e:
            logger.debug('ADFS token endpoint returned non-JSON: %s', e)
            return (
                TokenResult(
                    success=False, error='Invalid response from ADFS token endpoint'
                ),
                None,
            )

    def _extract_identifier_from_claim(self, value: str) -> Optional[str]:
        """Pull the user identifier out of a raw UPN or unique_name string.

        Resolution order:
        1. If ``user_id_pattern`` is set, use it as a regex.  The first capture
           group (if any) is returned; otherwise the full match.
        2. DOMAIN\\userid  — return the segment after the last backslash.
        3. userid@domain  — return the local part (before '@').
        4. Fall back to the whole trimmed value.
        """
        value = value.strip()
        if not value:
            return None

        pattern = self.config.user_id_pattern
        if pattern:
            m = re.search(pattern, value, re.IGNORECASE)
            if m:
                return (m.group(1) if m.lastindex else m.group(0)).strip() or None
            logger.debug(
                'ADFS identifier extraction: pattern %r did not match %r',
                pattern,
                value,
            )
            return None

        if '\\' in value:
            return value.rsplit('\\', 1)[-1].strip() or None

        if '@' in value:
            local = value.split('@', 1)[0].strip()
            return local or None

        return value or None

    def _resolve_login_email(
        self,
        email: Optional[str],
        upn: Optional[str],
        unique_name: Optional[str],
    ) -> Optional[str]:
        """Return the value to use as the login email for DB lookup.

        If a real ``email`` claim is present it is used as-is.  Otherwise the
        identifier is extracted from ``upn`` then ``unique_name``.  When the
        extracted value is a bare ID (no '@'), ``email_fallback_domain`` is
        appended to produce a valid email-shaped string.
        """
        if email:
            return email.lower()

        for candidate in (upn, unique_name):
            if not candidate:
                continue
            identifier = self._extract_identifier_from_claim(candidate)
            if not identifier:
                continue

            if '@' in identifier:
                return identifier.lower()

            if self.config.email_fallback_domain:
                domain = self.config.email_fallback_domain.lstrip('@')
                return f'{identifier}@{domain}'.lower()

            # No fallback domain — return the bare identifier so it can match
            # a username stored in the email column by convention.
            return identifier.lower()

        return None

    def _get_user_info_from_id_token(
        self, id_token: str, expected_nonce: Optional[str] = None
    ) -> Optional[UserInfo]:
        claims = self._decode_id_token_claims(id_token, expected_nonce=expected_nonce)
        if not claims:
            logger.debug('ADFS user_info: no claims (decode/validate failed)')
            return None

        raw_email = claims.get('email')
        upn = claims.get('upn')
        unique_name = claims.get('unique_name')
        if not raw_email and not upn and not unique_name:
            logger.debug(
                'ADFS user_info: no email/upn/unique_name claim present in id_token'
            )
            return None

        email = self._resolve_login_email(raw_email, upn, unique_name)
        logger.debug(
            'ADFS user_info resolved: email=%s (raw=%s) upn=%s unique_name=%s '
            'given_name=%s family_name=%s',
            email,
            raw_email,
            upn,
            unique_name,
            claims.get('given_name'),
            claims.get('family_name'),
        )

        first_name = claims.get('given_name')
        if not first_name and email and '@' in email:
            first_name = email.split('@')[0]

        return UserInfo(
            email=email,
            upn=upn,
            unique_name=unique_name,
            first_name=first_name,
            last_name=claims.get('family_name'),
            user_id=claims.get('sub') or claims.get('oid'),
            provider='microsoft_adfs',
            avatar_url=None,
            additional_info={
                'name': claims.get('name'),
                'groups': claims.get('groups'),
            },
        )

    def _decode_id_token_claims(
        self, id_token: str, expected_nonce: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        # Verify signature against the IdP's JWKS and enforce aud + exp/nbf.
        # iss is only enforced when expected_issuer is configured, because some
        # IdPs (e.g. Authentik in mixed http/https setups) advertise an iss host
        # that legitimately differs from the configured `authority`.
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(id_token)
            logger.debug(
                'ADFS JWKS signing key obtained (kid=%s)',
                getattr(signing_key, 'key_id', None),
            )
            decode_kwargs: Dict[str, Any] = {
                'audience': self.config.client_id,
                'leeway': self.config.clock_skew_seconds,
                'algorithms': _ALLOWED_ID_TOKEN_ALGS,
                'options': {
                    'verify_signature': True,
                    'verify_aud': True,
                    'verify_exp': True,
                    'verify_nbf': True,
                    'verify_iss': self.config.expected_issuer is not None,
                },
            }
            if self.config.expected_issuer:
                decode_kwargs['issuer'] = self.config.expected_issuer

            claims = jwt.decode(id_token, signing_key.key, **decode_kwargs)
            logger.debug('ADFS id_token claims decoded: %s', claims)

            if expected_nonce is not None and claims.get('nonce') != expected_nonce:
                logger.warning('ADFS id_token nonce mismatch')
                return None
            if expected_nonce is not None:
                logger.debug('ADFS id_token nonce matched expected value')

            return claims
        except jwt.PyJWTError as e:
            logger.warning('ADFS id_token JWT validation failed: %s', e)
            return None
        except Exception as e:
            logger.warning(
                'ADFS id_token decode failed (jwks_url=%s): %s', self.jwks_url, e
            )
            return None
