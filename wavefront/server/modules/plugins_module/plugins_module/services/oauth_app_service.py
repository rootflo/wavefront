from typing import Any, Dict, List, Optional
from uuid import UUID

from common_module.log.logger import logger
from db_repo_module.models.oauth_app import OAuthApp
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from flo_cloud.kms import FloKmsService
from mailer import EmailProviderABC, get_email_provider_factory

from plugins_module.utils.email_helper import (
    parse_provider,
    split_client_secret,
    validate_oauth_app_config,
)


class OAuthAppNotFound(Exception):
    pass


class OAuthAppService:
    """CRUD for platform OAuth client credentials.

    Holds the only path that decrypts a client secret, so provider instances are
    built here and handed to callers rather than exposing the secret itself.
    """

    def __init__(
        self,
        oauth_app_repository: SQLAlchemyRepository[OAuthApp],
        kms_service: FloKmsService,
    ):
        self._apps = oauth_app_repository
        self._kms = kms_service
        self._factory = get_email_provider_factory()

    async def create_app(
        self,
        name: str,
        provider: str,
        config: Dict[str, Any],
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        if ' ' in name:
            raise ValueError('OAuth app name cannot contain spaces')

        validate_oauth_app_config(provider, config)
        stored_config, client_secret = split_client_secret(config)

        existing = await self._apps.find_one(name=name)
        if existing:
            raise ValueError(f'An OAuth app named {name!r} already exists')

        encrypted_secret = self._kms.encrypt_for_storage(client_secret)

        app = await self._apps.create(
            name=name,
            provider=provider,
            description=description,
            config=stored_config,
            encrypted_client_secret=encrypted_secret,
        )

        self._factory.update_provider(str(app.id), parse_provider(provider), config)
        logger.info(f'Created OAuth app {name!r} for provider {provider!r}')
        return app.to_dict(include_config=True)

    async def update_app(
        self,
        app_id: UUID,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        app = await self._require_app(app_id)

        updates: Dict[str, Any] = {}
        if name is not None:
            if ' ' in name:
                raise ValueError('OAuth app name cannot contain spaces')
            clash = await self._apps.find_one(name=name)
            if clash and clash.id != app.id:
                raise ValueError(f'An OAuth app named {name!r} already exists')
            updates['name'] = name
        if description is not None:
            updates['description'] = description

        full_config: Optional[Dict[str, Any]] = None
        if config is not None:
            # An update may omit the secret to keep the stored one; merge it back
            # before validating so required-field checks see the whole config.
            candidate = dict(config)
            if not candidate.get('client_secret'):
                candidate['client_secret'] = self._kms.decrypt_from_storage(
                    app.encrypted_client_secret
                )
            validate_oauth_app_config(app.provider, candidate)
            stored_config, client_secret = split_client_secret(candidate)
            updates['config'] = stored_config
            updates['encrypted_client_secret'] = self._kms.encrypt_for_storage(
                client_secret
            )
            full_config = candidate

        if not updates:
            return app.to_dict(include_config=True)

        updated = await self._apps.find_one_and_update(
            {'id': app_id}, refresh=True, **updates
        )

        if full_config is not None:
            self._factory.update_provider(
                str(app_id), parse_provider(app.provider), full_config
            )

        return updated.to_dict(include_config=True)

    async def set_enabled(self, app_id: UUID, is_enabled: bool) -> Dict[str, Any]:
        await self._require_app(app_id)
        updated = await self._apps.find_one_and_update(
            {'id': app_id}, refresh=True, is_enabled=is_enabled
        )
        if not is_enabled:
            self._factory.remove_provider(str(app_id))
        return updated.to_dict()

    async def delete_app(self, app_id: UUID) -> None:
        app = await self._require_app(app_id)
        # Soft delete and free the unique name. Connections keep oauth_app_id;
        # RESTRICT blocks a hard delete while they exist. Reconnect mailboxes to
        # a new app if this one must stay deleted.
        freed_name = f'{app.name}__deleted__{app.id.hex[:8]}'
        await self._apps.find_one_and_update(
            {'id': app_id},
            name=freed_name,
            is_deleted=True,
            is_enabled=False,
        )
        self._factory.remove_provider(str(app_id))

    async def list_apps(self, provider: Optional[str] = None) -> List[Dict[str, Any]]:
        filters: Dict[str, Any] = {'is_deleted': False}
        if provider:
            filters['provider'] = provider
        apps = await self._apps.find(**filters)
        return [app.to_dict() for app in apps]

    async def get_app(self, app_id: UUID) -> Dict[str, Any]:
        app = await self._require_app(app_id)
        return app.to_dict(include_config=True)

    # ---- Provider access -------------------------------------------------

    async def get_provider_for_app(self, app: OAuthApp) -> EmailProviderABC:
        """Build (or reuse) the provider instance for an app row."""
        config = dict(app.config or {})
        config['client_secret'] = self._kms.decrypt_from_storage(
            app.encrypted_client_secret
        )
        return self._factory.get_provider(
            str(app.id), parse_provider(app.provider), config
        )

    async def find_enabled_apps(self, provider: str) -> List[OAuthApp]:
        return list(
            await self._apps.find(provider=provider, is_enabled=True, is_deleted=False)
        )

    async def _require_app(self, app_id: UUID) -> OAuthApp:
        app = await self._apps.find_one(id=app_id, is_deleted=False)
        if not app:
            raise OAuthAppNotFound(f'OAuth app {app_id} not found')
        return app
