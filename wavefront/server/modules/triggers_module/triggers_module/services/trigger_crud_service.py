from typing import List, Optional, Tuple
from uuid import UUID

from common_module.log.logger import logger
from db_repo_module.models.agent import Agent
from db_repo_module.models.agentic_trigger import AgenticTrigger
from db_repo_module.models.email_connection import EmailConnection
from db_repo_module.models.workflow import Workflow
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from mailer import EmailCapability, EmailProviderABC, GmailWatchConfig
from plugins_module.services.email_connection_service import (
    ConnectionNotFound,
    EmailConnectionError,
    EmailConnectionService,
)

from triggers_module.models.trigger_schemas import (
    CreateTriggerRequest,
    CreateTriggerResponse,
    TriggerResponse,
)

# Watching an inbox is a read: a trigger never needs to send.
WATCH_CAPABILITIES = [EmailCapability.READ]


class TriggerNotFound(Exception):
    pass


class InvalidTriggerState(Exception):
    pass


class EntityNotFound(Exception):
    pass


class TriggerCrudService:
    """Trigger lifecycle on top of an already-connected mailbox.

    Credentials are not this service's concern: a trigger names an
    `email_connection`, and `EmailConnectionService` owns consent and tokens. A
    trigger therefore goes straight to `active` once its watch is registered.
    """

    def __init__(
        self,
        trigger_repository: SQLAlchemyRepository[AgenticTrigger],
        agent_repository: SQLAlchemyRepository[Agent],
        workflow_repository: SQLAlchemyRepository[Workflow],
        email_connection_service: EmailConnectionService,
        gmail_watch_config: GmailWatchConfig,
    ):
        self._triggers = trigger_repository
        self._agents = agent_repository
        self._workflows = workflow_repository
        self._connections = email_connection_service
        self._gmail_watch_config = gmail_watch_config

    async def create_trigger(
        self, request: CreateTriggerRequest
    ) -> CreateTriggerResponse:
        await self._validate_entity(request.entity_type, request.entity_id)

        try:
            connection = await self._connections.require_active(request.connection_id)
        except ConnectionNotFound as exc:
            raise EntityNotFound(str(exc)) from exc
        except EmailConnectionError as exc:
            raise InvalidTriggerState(str(exc)) from exc

        if connection.provider != request.provider:
            raise InvalidTriggerState(
                f'Connection {connection.mailbox_email} is a {connection.provider} '
                f'mailbox, not {request.provider}'
            )

        trigger = await self._triggers.create(
            name=request.name,
            provider=request.provider,
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            namespace=request.namespace,
            status='pending_auth',
            filter_config=request.filter_config.model_dump(exclude_none=True),
            provider_config=request.provider_config,
            connection_id=connection.id,
        )

        try:
            provider_config = await self._start_watch(trigger, connection)
        except Exception as exc:
            # Kept as an `error` row rather than deleted so `retry_trigger` can
            # pick it up once the underlying problem is fixed.
            await self._triggers.find_one_and_update(
                {'id': trigger.id},
                status='error',
                last_error=f'start_watch failed: {exc}',
            )
            logger.exception(f'start_watch failed for trigger {trigger.id}')
            raise InvalidTriggerState(f'Failed to start inbox watch: {exc}') from exc

        updated = await self._triggers.find_one_and_update(
            {'id': trigger.id},
            status='active',
            provider_config=provider_config,
            last_error=None,
            refresh=True,
        )
        return CreateTriggerResponse(
            trigger_id=updated.id,
            status=updated.status,
            mailbox_email=connection.mailbox_email,
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
        """Re-register the inbox watch for a trigger in `error`.

        Use when the connection is fine but watch registration failed, such as a
        transient Pub/Sub IAM problem.
        """
        trigger = await self._triggers.find_one(id=trigger_id)
        if not trigger:
            raise TriggerNotFound(f'Trigger {trigger_id} not found')
        if trigger.status != 'error':
            raise InvalidTriggerState(
                f'Trigger {trigger_id} is in status {trigger.status!r}; '
                'retry only applies to triggers in error.'
            )

        try:
            connection = await self._connections.require_active(trigger.connection_id)
            provider_config = await self._start_watch(trigger, connection)
        except EmailConnectionError as exc:
            raise InvalidTriggerState(str(exc)) from exc
        except Exception as exc:
            await self._triggers.find_one_and_update(
                {'id': trigger_id},
                last_error=f'start_watch failed: {exc}',
            )
            logger.exception(f'retry_trigger: start_watch failed for {trigger_id}')
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

        if trigger.provider_config:
            try:
                provider, access_token, mailbox = await self._watch_context(
                    trigger.connection_id
                )
                # Planned for later: Gmail allows only one users.watch per
                # mailbox. Watches should be keyed by connection_id (shared
                # topic/history, fan-out to all active triggers on that
                # connection) and stop_watch should run only when deleting the
                # last trigger for the connection — not once per trigger.id.
                await provider.stop_watch(
                    access_token=access_token,
                    mailbox=mailbox,
                    provider_config=trigger.provider_config,
                )
            except Exception as exc:
                logger.warning(
                    f'stop_watch failed for trigger {trigger_id}; '
                    f'soft-deleting anyway: {exc}'
                )

        await self._triggers.find_one_and_update({'id': trigger_id}, status='deleted')
        # The connection outlives the trigger: other triggers, jobs and agents
        # may still be using that mailbox.

    async def _start_watch(
        self, trigger: AgenticTrigger, connection: EmailConnection
    ) -> dict:
        provider, access_token, mailbox = await self._watch_context(connection.id)
        watch_config = (
            self._gmail_watch_config if connection.provider == 'gmail' else None
        )
        # Planned for later: key watch_key by connection.id and route pushes to
        # every active trigger on that connection. Per-trigger watches can
        # replace each other on the same Gmail mailbox (one watch at a time).
        return await provider.start_watch(
            access_token=access_token,
            mailbox=mailbox,
            watch_key=str(trigger.id),
            watch_config=watch_config,
            push_endpoint_params={
                'trigger_id': str(trigger.id),
                'agentic_id': str(trigger.entity_id),
            },
        )

    async def _watch_context(
        self, connection_id: UUID
    ) -> Tuple[EmailProviderABC, str, str]:
        connection = await self._connections.require_active(connection_id)
        access_token, mailbox = await self._connections.get_access_token(
            connection_id, capabilities=WATCH_CAPABILITIES
        )
        provider = await self._connections.get_provider(connection)
        return provider, access_token, mailbox

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
            connection_id=trigger.connection_id,
            last_error=trigger.last_error,
            created_at=trigger.created_at,
            updated_at=trigger.updated_at,
        )
