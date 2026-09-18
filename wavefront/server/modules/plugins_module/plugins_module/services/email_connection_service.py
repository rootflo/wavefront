from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from common_module.common_cache import CommonCache
from common_module.log.logger import logger
from db_repo_module.models.email_connection import EmailConnection
from db_repo_module.models.oauth_app import OAuthApp
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from flo_cloud.kms import FloKmsService
from mailer import EmailCapability, EmailProviderABC, TokenBundle
from sqlalchemy import update

from plugins_module.services.oauth_app_service import OAuthAppService
from plugins_module.utils.email_helper import (
    consume_email_oauth_state,
    issue_email_oauth_state,
    parse_capabilities,
    parse_provider,
)

# Refresh a little early so a token cannot expire between the check and the API
# call it was fetched for.
TOKEN_REFRESH_SKEW = timedelta(seconds=60)


class EmailConnectionError(Exception):
    pass


class ConnectionNotFound(EmailConnectionError):
    pass


class InvalidConnectionState(EmailConnectionError):
    pass


class EmailAppNotConfigured(EmailConnectionError):
    """No usable OAuth app is attached, so nothing can be signed."""


class MailboxMismatch(EmailConnectionError):
    """Consent came back for a different mailbox than the one being connected."""


class InsufficientScope(EmailConnectionError):
    """The connection was never granted what this action needs.

    Carries the capabilities to ask for so the caller can send the user back
    through consent instead of guessing.
    """

    def __init__(
        self,
        message: str,
        connection_id: UUID,
        missing: Sequence[EmailCapability],
    ):
        super().__init__(message)
        self.connection_id = connection_id
        self.missing = list(missing)

    @property
    def required_capabilities(self) -> List[str]:
        return [capability.value for capability in self.missing]


class EmailConnectionService:
    """The single source of mailbox credentials.

    Every email feature comes through here: triggers to watch an inbox, the agent
    tool and scheduled jobs to send, platform mail via the primary connection.
    Tokens are only ever handed out as short-lived access tokens, so no caller
    needs to know how they are stored or refreshed.
    """

    def __init__(
        self,
        connection_repository: SQLAlchemyRepository[EmailConnection],
        oauth_app_repository: SQLAlchemyRepository[OAuthApp],
        oauth_app_service: OAuthAppService,
        kms_service: FloKmsService,
        cache_manager: CommonCache,
    ):
        self._connections = connection_repository
        self._apps = oauth_app_repository
        self._app_service = oauth_app_service
        self._kms = kms_service
        self._cache = cache_manager

    # ---- Lifecycle -------------------------------------------------------

    async def create_connection(
        self,
        name: str,
        provider: str,
        capabilities: Sequence[str],
        oauth_app_id: UUID,
        created_by: Optional[str] = None,
        session_id: Optional[str] = None,
        success_redirect_url: Optional[str] = None,
        failure_redirect_url: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], str]:
        """Create a placeholder connection and the consent URL that fills it in.

        The mailbox address is unknown until the user consents, so the row starts
        with a blank address and is keyed only by its id.
        """
        parse_provider(provider)
        requested = parse_capabilities(list(capabilities))

        app = await self._resolve_app_for_provider(provider, oauth_app_id)
        connection = await self._connections.create(
            name=name,
            provider=provider,
            oauth_app_id=app.id,
            mailbox_email='',
            status='pending_auth',
            created_by=created_by,
        )

        provider_impl = await self._app_service.get_provider_for_app(app)
        consent_url = provider_impl.build_consent_url(
            state=issue_email_oauth_state(
                self._cache,
                connection_id=connection.id,
                session_id=session_id or '',
                user_id=created_by,
                success_redirect_url=success_redirect_url,
                failure_redirect_url=failure_redirect_url,
            ),
            scopes=provider_impl.scopes_for(requested),
        )
        return connection.to_dict(), consent_url

    async def build_authorize_url(
        self,
        connection_id: UUID,
        capabilities: Sequence[str],
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        success_redirect_url: Optional[str] = None,
        failure_redirect_url: Optional[str] = None,
    ) -> str:
        """Consent URL for a new grant or a scope upgrade.

        Already-granted capabilities are folded in, so upgrading to `send` never
        silently drops `read`.
        """
        connection = await self._require_connection(connection_id)
        requested = parse_capabilities(list(capabilities))

        app = await self._require_app(connection)
        provider_impl = await self._app_service.get_provider_for_app(app)

        granted = provider_impl.capabilities_for(connection.granted_scopes)
        merged = list(granted)
        for capability in requested:
            if capability not in merged:
                merged.append(capability)

        return provider_impl.build_consent_url(
            state=issue_email_oauth_state(
                self._cache,
                connection_id=connection.id,
                session_id=session_id or '',
                user_id=user_id or connection.created_by,
                success_redirect_url=success_redirect_url,
                failure_redirect_url=failure_redirect_url,
            ),
            scopes=provider_impl.scopes_for(merged),
        )

    def consume_oauth_state(
        self,
        state: str,
        *,
        session_id: Optional[str] = None,
    ) -> Tuple[UUID, Optional[str], Optional[str], Optional[str]]:
        """Validate and consume opaque OAuth state before exchanging the code."""
        return consume_email_oauth_state(self._cache, state, session_id=session_id)

    async def complete_oauth(self, connection_id: UUID, code: str) -> Dict[str, Any]:
        connection = await self._require_connection(connection_id)
        app = await self._require_app(connection)
        provider_impl = await self._app_service.get_provider_for_app(app)

        bundle = await provider_impl.exchange_code(code)

        mailbox = (bundle.external_account_id or '').strip().lower()
        if not mailbox:
            raise InvalidConnectionState(
                'Provider did not report which mailbox consented'
            )

        # Reconnecting an existing connection must not silently point at someone
        # else's inbox: triggers and tools already reference this id.
        if connection.mailbox_email and connection.mailbox_email.lower() != mailbox:
            raise MailboxMismatch(
                f'This connection is bound to {connection.mailbox_email}, but '
                f'consent was granted for {mailbox}. Sign in with the correct '
                'account or create a separate connection.'
            )

        await self._assert_mailbox_available(connection, mailbox)

        # Google may omit refresh_token on re-consent when one was already
        # issued; keep the stored token in that case rather than wiping it.
        if bundle.refresh_token:
            encrypted_refresh_token = self._kms.encrypt_for_storage(
                bundle.refresh_token
            )
        else:
            encrypted_refresh_token = connection.encrypted_refresh_token

        if not encrypted_refresh_token:
            raise InvalidConnectionState(
                'Provider did not return a refresh token and none is stored for '
                'this connection. Re-authorize with consent to restore access.'
            )

        updated = await self._connections.find_one_and_update(
            {'id': connection_id},
            refresh=True,
            mailbox_email=mailbox,
            status='active',
            granted_scopes=bundle.scopes,
            encrypted_refresh_token=encrypted_refresh_token,
            encrypted_access_token=self._kms.encrypt_for_storage(bundle.access_token),
            token_expires_at=bundle.expires_at,
            last_error=None,
        )
        logger.info(f'Email connection {connection_id} activated for {mailbox}')
        return updated.to_dict()

    async def list_connections(
        self,
        provider: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        filters: Dict[str, Any] = {}
        if provider:
            filters['provider'] = provider
        if status:
            filters['status'] = status
        rows = await self._connections.find(limit=limit, **filters)
        return [row.to_dict() for row in rows if status or row.status != 'deleted']

    async def get_connection(self, connection_id: UUID) -> Dict[str, Any]:
        connection = await self._require_connection(connection_id)
        return connection.to_dict()

    async def verify_connection(self, connection_id: UUID) -> Dict[str, Any]:
        """Prove tokens still work against the provider.

        Refreshes when needed, calls the provider profile endpoint, and updates
        `status` / `last_error` so the UI reflects live connectivity rather than
        the last opportunistic refresh.
        """
        connection = await self._require_connection(connection_id)
        if connection.status == 'pending_auth':
            raise InvalidConnectionState(
                f'Connection {connection_id} has not completed consent yet'
            )

        try:
            access_token, mailbox = await self._access_token_for(connection)
            provider = await self.get_provider(connection)
            reported = await provider.get_account_email(access_token)
        except InsufficientScope:
            raise
        except Exception as exc:
            await self._connections.find_one_and_update(
                {'id': connection_id},
                status='error',
                last_error=f'verify failed: {exc}',
            )
            logger.exception(f'Verify failed for connection {connection_id}')
            raise InvalidConnectionState(
                f'Verify failed for {connection.mailbox_email or connection_id}: {exc}'
            ) from exc

        reported_email = (reported or '').strip().lower()
        if reported_email and mailbox and reported_email != mailbox.lower():
            message = (
                f'Token belongs to {reported_email}, but this connection is bound '
                f'to {mailbox}'
            )
            await self._connections.find_one_and_update(
                {'id': connection_id},
                status='error',
                last_error=message,
            )
            raise MailboxMismatch(message)

        updated = await self._connections.find_one_and_update(
            {'id': connection_id},
            refresh=True,
            status='active',
            last_error=None,
        )
        logger.info(f'Email connection {connection_id} verified for {mailbox}')
        return updated.to_dict()

    async def delete_connection(self, connection_id: UUID) -> None:
        connection = await self._require_connection(connection_id)
        # Tokens go immediately; the row is kept so features referencing it can
        # report a deleted connection rather than a dangling id.
        await self._connections.find_one_and_update(
            {'id': connection_id},
            status='deleted',
            is_primary=False,
            encrypted_refresh_token=None,
            encrypted_access_token=None,
            token_expires_at=None,
        )
        logger.info(
            f'Email connection {connection_id} ({connection.mailbox_email}) deleted'
        )

    # ---- Primary sender --------------------------------------------------

    async def get_primary(self) -> EmailConnection:
        connection = await self._connections.find_one(is_primary=True)
        if not connection:
            raise EmailAppNotConfigured(
                'No primary email connection is set. Connect a mailbox and mark '
                'it primary to enable platform email.'
            )
        if connection.status != 'active':
            raise InvalidConnectionState(
                f'The primary email connection ({connection.mailbox_email}) is '
                f'{connection.status!r} and cannot send.'
            )
        return connection

    async def set_primary(self, connection_id: UUID) -> Dict[str, Any]:
        connection = await self._require_connection(connection_id)
        if connection.status != 'active':
            raise InvalidConnectionState(
                f'Connection {connection_id} is {connection.status!r}; only an '
                'active connection can be the primary sender.'
            )

        app = await self._require_app(connection)
        provider_impl = await self._app_service.get_provider_for_app(app)
        granted = provider_impl.capabilities_for(connection.granted_scopes)
        if EmailCapability.SEND not in granted:
            raise InsufficientScope(
                f'Connection {connection.mailbox_email} has not been granted '
                'permission to send email, so it cannot be the primary sender.',
                connection_id=connection_id,
                missing=[EmailCapability.SEND],
            )

        # One transaction, and the demotion first: a unique index permits only
        # one primary row, so an interleaved swap would collide.
        async with self._connections.session() as session:
            await session.execute(
                update(EmailConnection)
                .where(
                    EmailConnection.is_primary.is_(True),
                    EmailConnection.id != connection_id,
                )
                .values(is_primary=False)
            )
            await session.execute(
                update(EmailConnection)
                .where(EmailConnection.id == connection_id)
                .values(is_primary=True)
            )
            await session.commit()

        updated = await self._require_connection(connection_id)
        logger.info(f'Primary email connection set to {updated.mailbox_email}')
        return updated.to_dict()

    # ---- Token access ----------------------------------------------------

    async def get_access_token(
        self,
        connection_id: UUID,
        capabilities: Sequence[EmailCapability] = (),
    ) -> Tuple[str, str]:
        """A usable access token and the mailbox it belongs to.

        Refreshes and persists when the cached token has expired, and refuses
        outright when the connection was never granted `capabilities`.
        """
        connection = await self._require_connection(connection_id)
        return await self._access_token_for(connection, capabilities)

    async def get_provider(self, connection: EmailConnection) -> EmailProviderABC:
        app = await self._require_app(connection)
        return await self._app_service.get_provider_for_app(app)

    async def require_active(self, connection_id: UUID) -> EmailConnection:
        connection = await self._require_connection(connection_id)
        if connection.status != 'active':
            raise InvalidConnectionState(
                f'Connection {connection_id} is {connection.status!r}, not active'
            )
        return connection

    async def resolve_sender(self, connection_id: Optional[UUID]) -> EmailConnection:
        """An explicit connection when given, otherwise the primary one.

        There is no configuration fallback: an unresolvable sender is an error
        rather than a silent switch to some other mailbox.
        """
        if connection_id is None:
            return await self.get_primary()
        return await self.require_active(connection_id)

    async def _access_token_for(
        self,
        connection: EmailConnection,
        capabilities: Sequence[EmailCapability] = (),
    ) -> Tuple[str, str]:
        app = await self._require_app(connection)
        provider_impl = await self._app_service.get_provider_for_app(app)

        if capabilities:
            self._assert_capabilities(connection, provider_impl, capabilities)

        now = datetime.now(timezone.utc)
        if (
            connection.encrypted_access_token
            and connection.token_expires_at
            and self._as_aware(connection.token_expires_at) - TOKEN_REFRESH_SKEW > now
        ):
            token = self._kms.decrypt_from_storage(connection.encrypted_access_token)
            if token:
                return token, connection.mailbox_email

        refresh_token = (
            self._kms.decrypt_from_storage(connection.encrypted_refresh_token)
            if connection.encrypted_refresh_token
            else None
        )
        if not refresh_token:
            raise InvalidConnectionState(
                f'Connection {connection.id} has no refresh token; reconnect the '
                'mailbox to restore access.'
            )

        try:
            bundle: TokenBundle = await provider_impl.refresh_access_token(
                refresh_token
            )
        except Exception as exc:
            await self._connections.find_one_and_update(
                {'id': connection.id},
                status='error',
                last_error=f'token refresh failed: {exc}',
            )
            logger.exception(f'Token refresh failed for connection {connection.id}')
            raise

        updates: Dict[str, Any] = {
            'encrypted_access_token': self._kms.encrypt_for_storage(
                bundle.access_token
            ),
            'token_expires_at': bundle.expires_at,
            'last_error': None,
        }
        # Microsoft rotates refresh tokens on use; storing the new one keeps the
        # connection alive past the old token's lifetime.
        if bundle.refresh_token and bundle.refresh_token != refresh_token:
            updates['encrypted_refresh_token'] = self._kms.encrypt_for_storage(
                bundle.refresh_token
            )
        if bundle.scopes:
            updates['granted_scopes'] = bundle.scopes

        await self._connections.find_one_and_update({'id': connection.id}, **updates)

        if not bundle.access_token:
            raise InvalidConnectionState(
                f'Provider returned no access token for connection {connection.id}'
            )
        return bundle.access_token, connection.mailbox_email

    def _assert_capabilities(
        self,
        connection: EmailConnection,
        provider_impl: EmailProviderABC,
        capabilities: Sequence[EmailCapability],
    ) -> None:
        granted = provider_impl.capabilities_for(connection.granted_scopes)
        missing = [
            capability for capability in capabilities if capability not in granted
        ]
        if missing:
            names = ', '.join(capability.value for capability in missing)
            raise InsufficientScope(
                f'Connection {connection.mailbox_email} was not granted: {names}. '
                'Re-authorize the connection with these capabilities.',
                connection_id=connection.id,
                missing=missing,
            )

    # ---- Internals -------------------------------------------------------

    async def _require_connection(self, connection_id: UUID) -> EmailConnection:
        connection = await self._connections.find_one(id=connection_id)
        if not connection or connection.status == 'deleted':
            raise ConnectionNotFound(f'Email connection {connection_id} not found')
        return connection

    async def _require_app(self, connection: EmailConnection) -> OAuthApp:
        app = await self._apps.find_one(
            id=connection.oauth_app_id, is_deleted=False, is_enabled=True
        )
        if not app:
            raise EmailAppNotConfigured(
                f'OAuth app {connection.oauth_app_id} not found or disabled'
            )
        return app

    async def _resolve_app_for_provider(
        self, provider: str, oauth_app_id: UUID
    ) -> OAuthApp:
        app = await self._apps.find_one(
            id=oauth_app_id, is_deleted=False, is_enabled=True
        )
        if not app:
            raise EmailAppNotConfigured(
                f'OAuth app {oauth_app_id} not found or disabled'
            )
        if app.provider != provider:
            raise EmailAppNotConfigured(
                f'OAuth app {app.name!r} is for {app.provider}, not {provider}'
            )
        return app

    async def _assert_mailbox_available(
        self, connection: EmailConnection, mailbox: str
    ) -> None:
        existing = await self._connections.find_one(
            provider=connection.provider, mailbox_email=mailbox
        )
        if existing and existing.id != connection.id and existing.status != 'deleted':
            raise MailboxMismatch(
                f'{mailbox} is already connected as {existing.name!r}. Re-authorize '
                'that connection instead of creating a second one.'
            )

    @staticmethod
    def _as_aware(value: datetime) -> datetime:
        # Timestamps read back from Postgres can be naive depending on the
        # driver; compare in UTC either way.
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
