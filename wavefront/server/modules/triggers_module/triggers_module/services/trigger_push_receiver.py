import uuid
from typing import Any, Dict, Optional
from uuid import UUID

from common_module.log.logger import logger
from db_repo_module.models.agentic_trigger import AgenticTrigger
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository

from agents_module.utils.celery_client import get_celery_client
from triggers_module.providers.gmail.pubsub_signature import (
    PubSubPushVerifier,
    PubSubSignatureError,
)
from triggers_module.providers.registry import TriggerProviderRegistry


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
        pubsub_verifier: PubSubPushVerifier,
        provider_registry: TriggerProviderRegistry,
    ):
        self._triggers = trigger_repository
        self._verifier = pubsub_verifier
        self._registry = provider_registry

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

        if trigger.provider == 'gmail':
            oidc_audience = (trigger.provider_config or {}).get('oidc_audience')
            if oidc_audience:
                try:
                    self._verifier.verify(
                        authorization_header, expected_audience=oidc_audience
                    )
                except PubSubSignatureError as exc:
                    logger.warning(
                        f'Pub/Sub signature verification failed for trigger {trigger_id}: {exc}'
                    )
                    return {'status': 'ignored', 'reason': 'invalid_signature'}

        # Layer-2 dedup: skip pushes whose cursor we've already processed.
        provider = self._registry.get(trigger.provider)
        incoming_cursor = provider.extract_push_cursor(raw_payload)
        stored_cursor = (trigger.provider_config or {}).get('history_id')
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
