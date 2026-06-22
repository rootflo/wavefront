from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from common_module.log.logger import logger
from db_repo_module.models.agent import Agent
from db_repo_module.models.agentic_trigger import AgenticTrigger
from db_repo_module.models.agentic_trigger_credential import AgenticTriggerCredential
from db_repo_module.models.workflow import Workflow
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository

from triggers_module.models.trigger_schemas import (
    CreateTriggerRequest,
    CreateTriggerResponse,
    TriggerResponse,
)
from triggers_module.providers.base import TokenBundle, TriggerProvider
from triggers_module.providers.registry import TriggerProviderRegistry
from triggers_module.utils.token_crypto import TokenCrypto


class TriggerNotFound(Exception):
    pass


class InvalidTriggerState(Exception):
    pass


class EntityNotFound(Exception):
    pass


class TriggerCrudService:
    def __init__(
        self,
        trigger_repository: SQLAlchemyRepository[AgenticTrigger],
        credential_repository: SQLAlchemyRepository[AgenticTriggerCredential],
        agent_repository: SQLAlchemyRepository[Agent],
        workflow_repository: SQLAlchemyRepository[Workflow],
        provider_registry: TriggerProviderRegistry,
        token_crypto: TokenCrypto,
    ):
        self._triggers = trigger_repository
        self._credentials = credential_repository
        self._agents = agent_repository
        self._workflows = workflow_repository
        self._registry = provider_registry
        self._crypto = token_crypto

    async def create_trigger(
        self, request: CreateTriggerRequest
    ) -> CreateTriggerResponse:
        await self._validate_entity(request.entity_type, request.entity_id)
        provider = self._registry.get(request.provider)

        trigger = await self._triggers.create(
            name=request.name,
            provider=request.provider,
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            namespace=request.namespace,
            status='pending_auth' if provider.requires_oauth else 'active',
            filter_config=request.filter_config.model_dump(exclude_none=True),
            provider_config=request.provider_config,
        )

        consent_url: Optional[str] = None
        if provider.requires_oauth:
            consent_url = provider.build_consent_url(trigger_id=str(trigger.id))

        return CreateTriggerResponse(
            trigger_id=trigger.id,
            status=trigger.status,
            consent_url=consent_url,
        )

    async def complete_oauth(self, state: str, code: str) -> TriggerResponse:
        try:
            trigger_id = UUID(state)
        except ValueError as exc:
            raise InvalidTriggerState(f'Invalid OAuth state: {state}') from exc

        trigger = await self._triggers.find_one(id=trigger_id)
        if not trigger:
            raise TriggerNotFound(f'Trigger {trigger_id} not found')
        if trigger.status != 'pending_auth':
            raise InvalidTriggerState(
                f'Trigger {trigger_id} is in status {trigger.status!r}, '
                'cannot complete OAuth'
            )

        provider = self._registry.get(trigger.provider)
        token_bundle = await provider.exchange_oauth_code(
            code=code, trigger_id=str(trigger_id)
        )

        credential = await self._upsert_credential(trigger.provider, token_bundle)

        # Link the credential to the trigger immediately so a later
        # `start_subscription` failure leaves a retry-able state instead of an
        # orphaned credential.
        await self._triggers.find_one_and_update(
            {'id': trigger_id}, credential_id=credential.id
        )

        try:
            provider_config = await provider.start_subscription(
                trigger_id=str(trigger_id),
                access_token=token_bundle.access_token or '',
                external_account_id=token_bundle.external_account_id,
                agentic_id=str(trigger.entity_id),
            )
        except Exception as exc:
            await self._triggers.find_one_and_update(
                {'id': trigger_id},
                status='error',
                last_error=f'start_subscription failed: {exc}',
            )
            logger.exception(f'start_subscription failed for trigger {trigger_id}')
            raise

        updated = await self._triggers.find_one_and_update(
            {'id': trigger_id},
            status='active',
            provider_config=provider_config,
            last_error=None,
            refresh=True,
        )
        return self._to_response(updated)

    async def _upsert_credential(
        self, provider: str, token_bundle: TokenBundle
    ) -> AgenticTriggerCredential:
        existing = await self._credentials.find_one(
            provider=provider,
            external_account_id=token_bundle.external_account_id,
        )

        encrypted_refresh = self._crypto.encrypt(token_bundle.refresh_token)
        encrypted_access = self._crypto.encrypt(token_bundle.access_token)
        expires_at = token_bundle.expires_at

        if existing:
            return await self._credentials.find_one_and_update(
                {'id': existing.id},
                encrypted_refresh_token=encrypted_refresh,
                encrypted_access_token=encrypted_access,
                token_expires_at=expires_at,
                scopes=token_bundle.scopes,
                refresh=True,
            )

        return await self._credentials.create(
            provider=provider,
            external_account_id=token_bundle.external_account_id,
            encrypted_refresh_token=encrypted_refresh,
            encrypted_access_token=encrypted_access,
            token_expires_at=expires_at,
            scopes=token_bundle.scopes,
        )

    async def list_triggers(
        self,
        provider: Optional[str] = None,
        namespace: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[TriggerResponse]:
        filters = {}
        if provider:
            filters['provider'] = provider
        if namespace:
            filters['namespace'] = namespace
        if status:
            filters['status'] = status
        rows = await self._triggers.find(limit=limit, **filters)
        return [self._to_response(row) for row in rows]

    async def get_trigger(self, trigger_id: UUID) -> TriggerResponse:
        trigger = await self._triggers.find_one(id=trigger_id)
        if not trigger:
            raise TriggerNotFound(f'Trigger {trigger_id} not found')
        return self._to_response(trigger)

    async def pause_trigger(self, trigger_id: UUID) -> TriggerResponse:
        updated = await self._triggers.find_one_and_update(
            {'id': trigger_id}, status='paused', refresh=True
        )
        if not updated:
            raise TriggerNotFound(f'Trigger {trigger_id} not found')
        return self._to_response(updated)

    async def resume_trigger(self, trigger_id: UUID) -> TriggerResponse:
        updated = await self._triggers.find_one_and_update(
            {'id': trigger_id}, status='active', refresh=True
        )
        if not updated:
            raise TriggerNotFound(f'Trigger {trigger_id} not found')
        return self._to_response(updated)

    async def retry_trigger(self, trigger_id: UUID) -> TriggerResponse:
        """Re-runs `start_subscription` for an `error` trigger using its already-
        stored credential. Use when the original OAuth completed but the upstream
        subscription setup failed (e.g. transient Pub/Sub IAM issue)."""
        trigger = await self._triggers.find_one(id=trigger_id)
        if not trigger:
            raise TriggerNotFound(f'Trigger {trigger_id} not found')
        if trigger.status != 'error':
            raise InvalidTriggerState(
                f'Trigger {trigger_id} is in status {trigger.status!r}; '
                'retry only applies to triggers in error.'
            )
        if not trigger.credential_id:
            raise InvalidTriggerState(
                f'Trigger {trigger_id} has no credential; cannot retry without OAuth.'
            )

        provider = self._registry.get(trigger.provider)
        access_token, external_account_id = await self._fresh_access_token(
            trigger.credential_id, provider
        )

        try:
            provider_config = await provider.start_subscription(
                trigger_id=str(trigger_id),
                access_token=access_token,
                external_account_id=external_account_id,
                agentic_id=str(trigger.entity_id),
            )
        except Exception as exc:
            await self._triggers.find_one_and_update(
                {'id': trigger_id},
                last_error=f'start_subscription failed: {exc}',
            )
            logger.exception(
                f'retry_trigger: start_subscription failed for {trigger_id}'
            )
            raise

        updated = await self._triggers.find_one_and_update(
            {'id': trigger_id},
            status='active',
            provider_config=provider_config,
            last_error=None,
            refresh=True,
        )
        return self._to_response(updated)

    async def delete_trigger(self, trigger_id: UUID) -> None:
        trigger = await self._triggers.find_one(id=trigger_id)
        if not trigger:
            raise TriggerNotFound(f'Trigger {trigger_id} not found')

        provider = self._registry.get(trigger.provider)
        if trigger.credential_id and trigger.provider_config:
            try:
                access_token, external_account_id = await self._fresh_access_token(
                    trigger.credential_id, provider
                )
                await provider.stop_subscription(
                    provider_config=trigger.provider_config,
                    access_token=access_token,
                    external_account_id=external_account_id,
                )
            except Exception as exc:
                logger.warning(
                    f'stop_subscription failed for trigger {trigger_id}; '
                    f'soft-deleting anyway: {exc}'
                )

        await self._triggers.find_one_and_update({'id': trigger_id}, status='deleted')

        if trigger.credential_id:
            other_refs = await self._triggers.count(credential_id=trigger.credential_id)
            if other_refs <= 1:
                await self._credentials.delete_all(id=trigger.credential_id)

    async def _fresh_access_token(
        self, credential_id: UUID, provider: TriggerProvider
    ) -> tuple[str, str]:
        credential = await self._credentials.find_one(id=credential_id)
        if not credential:
            raise InvalidTriggerState(f'Credential {credential_id} not found')

        now = datetime.now(timezone.utc)
        if (
            credential.encrypted_access_token
            and credential.token_expires_at
            and credential.token_expires_at > now
        ):
            return (
                self._crypto.decrypt(credential.encrypted_access_token),
                credential.external_account_id,
            )

        refresh_token = self._crypto.decrypt(credential.encrypted_refresh_token)
        bundle = await provider.refresh_access_token(refresh_token)
        await self._credentials.find_one_and_update(
            {'id': credential_id},
            encrypted_access_token=self._crypto.encrypt(bundle.access_token),
            token_expires_at=bundle.expires_at,
        )
        return bundle.access_token or '', credential.external_account_id

    async def _validate_entity(self, entity_type: str, entity_id: UUID) -> None:
        if entity_type == 'agent':
            row = await self._agents.find_one(id=entity_id)
        elif entity_type == 'workflow':
            row = await self._workflows.find_one(id=entity_id)
        else:
            raise InvalidTriggerState(f'Unknown entity_type: {entity_type}')
        if not row:
            raise EntityNotFound(f'{entity_type} {entity_id} not found')

    def _to_response(self, trigger: AgenticTrigger) -> TriggerResponse:
        return TriggerResponse(
            id=trigger.id,
            name=trigger.name,
            provider=trigger.provider,
            entity_type=trigger.entity_type,
            entity_id=trigger.entity_id,
            namespace=trigger.namespace,
            status=trigger.status,
            filter_config=trigger.filter_config,
            provider_config=trigger.provider_config,
            credential_id=trigger.credential_id,
            last_error=trigger.last_error,
            created_at=trigger.created_at,
            updated_at=trigger.updated_at,
        )
