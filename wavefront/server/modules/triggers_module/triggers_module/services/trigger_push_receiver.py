import uuid
from typing import Any, Dict, Optional
from uuid import UUID

from agents_module.utils.celery_client import get_celery_client
from common_module.log.logger import logger
from db_repo_module.models.agentic_trigger import AgenticTrigger
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from mailer import PushSignatureError
from plugins_module.services.email_connection_service import (
    EmailConnectionError,
    EmailConnectionService,
)

_TRIGGER_EVENT_TASK_NAME = (
    'celery_worker.tasks.trigger_event_task.process_trigger_event_task'
)


class TriggerMismatch(Exception):
    pass


class TriggerPushReceiver:
    """Floware-side handler for `POST /triggers/{trigger_id}/{agentic_id}/invoke`.

    Verifies the upstream provider's signature, short-circuits stale pushes
    using the provider's cursor, then enqueues a Celery task to do the heavy
    lifting (Gmail history list, message fetch, attachment download, regex
    filter, v3 dispatch). Returns fast; no Gmail I/O happens here. Per-message
    idempotency lives in the Celery task via the unique
    `(trigger_id, provider_event_id)` constraint on `agentic_trigger_events`.
    """

    def __init__(
        self,
        trigger_repository: SQLAlchemyRepository[AgenticTrigger],
        email_connection_service: EmailConnectionService,
    ):
        self._triggers = trigger_repository
        self._connections = email_connection_service

    async def handle_push(
        self,
        trigger_id: UUID,
        agentic_id: UUID,
        raw_payload: Dict[str, Any],
        authorization_header: Optional[str],
    ) -> Dict[str, Any]:
        trigger = await self._triggers.find_one(id=trigger_id)
        if not trigger:
            return {'status': 'ignored', 'reason': 'trigger_not_found'}

        if trigger.status != 'active':
            return {'status': 'ignored', 'reason': f'trigger_status_{trigger.status}'}

        if trigger.entity_id != agentic_id:
            raise TriggerMismatch(
                f'Path agentic_id {agentic_id} does not match trigger entity_id '
                f'{trigger.entity_id}'
            )

        try:
            connection = await self._connections.require_active(trigger.connection_id)
            provider = await self._connections.get_provider(connection)
        except EmailConnectionError as exc:
            logger.warning(
                f'Cannot resolve email connection for trigger {trigger_id}: {exc}'
            )
            return {'status': 'ignored', 'reason': 'connection_unavailable'}

        # Only verifiable when the watch was registered with an OIDC push config;
        # without an audience/identity there is no signature to check.
        provider_config = trigger.provider_config or {}
        oidc_audience = provider_config.get('oidc_audience')
        oidc_service_account_email = provider_config.get('oidc_service_account_email')
        if not oidc_audience or not oidc_service_account_email:
            logger.warning(
                f'Missing OIDC push binding for trigger {trigger_id}; refusing push'
            )
            return {'status': 'ignored', 'reason': 'missing_oidc_audience'}
        try:
            provider.verify_push(
                authorization_header,
                expected_audience=oidc_audience,
                expected_service_account_email=oidc_service_account_email,
            )
        except PushSignatureError as exc:
            logger.warning(
                f'Push signature verification failed for trigger {trigger_id}: {exc}'
            )
            return {'status': 'ignored', 'reason': 'invalid_signature'}

        # Layer-2 dedup: skip pushes whose cursor we've already processed.
        incoming_cursor = provider.extract_push_cursor(raw_payload)
        stored_cursor = provider_config.get('history_id')
        if (
            incoming_cursor is not None
            and stored_cursor is not None
            and int(incoming_cursor) <= int(stored_cursor)
        ):
            return {
                'status': 'ignored',
                'reason': 'stale_cursor',
                'incoming_cursor': int(incoming_cursor),
                'stored_cursor': int(stored_cursor),
            }

        push_message_id = (raw_payload.get('message') or {}).get('messageId') or str(
            uuid.uuid4()
        )

        get_celery_client().send_task(
            _TRIGGER_EVENT_TASK_NAME,
            kwargs={
                'trigger_id': str(trigger_id),
                'raw_payload': raw_payload,
                'push_message_id': push_message_id,
            },
        )

        return {'status': 'queued', 'push_message_id': push_message_id}
