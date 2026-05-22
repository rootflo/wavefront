import re
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import UUID

from agents_module.services.async_agentic_execution_service import (
    AsyncAgenticExecutionService,
)
from common_module.log.logger import logger
from db_repo_module.models.agentic_trigger import AgenticTrigger
from db_repo_module.models.agentic_trigger_credential import AgenticTriggerCredential
from db_repo_module.models.agentic_trigger_event import AgenticTriggerEvent
from db_repo_module.models.workflow import Workflow
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository

from triggers_module.providers.base import (
    NormalizedEmailEvent,
    TriggerProvider,
)
from triggers_module.providers.registry import TriggerProviderRegistry
from triggers_module.utils.input_builder import (
    EmailTooLargeError,
    build_inference_inputs,
)
from triggers_module.utils.token_crypto import TokenCrypto


class TriggerEventProcessor:
    """Worker-side processor: fetches Gmail messages, filters them, and feeds
    matching ones into the existing v3 async-execution pipeline."""

    def __init__(
        self,
        trigger_repository: SQLAlchemyRepository[AgenticTrigger],
        credential_repository: SQLAlchemyRepository[AgenticTriggerCredential],
        event_repository: SQLAlchemyRepository[AgenticTriggerEvent],
        workflow_repository: SQLAlchemyRepository[Workflow],
        provider_registry: TriggerProviderRegistry,
        token_crypto: TokenCrypto,
        async_execution_service: AsyncAgenticExecutionService,
    ):
        self._triggers = trigger_repository
        self._credentials = credential_repository
        self._events = event_repository
        self._workflows = workflow_repository
        self._registry = provider_registry
        self._crypto = token_crypto
        self._async_exec = async_execution_service

    async def process(
        self, trigger_id: UUID, raw_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        trigger = await self._triggers.find_one(id=trigger_id)
        if not trigger:
            return {'status': 'ignored', 'reason': 'trigger_not_found'}
        if trigger.status != 'active':
            return {'status': 'ignored', 'reason': f'trigger_status_{trigger.status}'}
        if not trigger.credential_id:
            return {'status': 'ignored', 'reason': 'no_credential'}

        provider = self._registry.get(trigger.provider)
        access_token, _ = await self._fresh_access_token(
            trigger.credential_id, provider
        )

        events = await provider.fetch_events(
            access_token=access_token,
            provider_config=trigger.provider_config or {},
            raw_push_payload=raw_payload,
        )

        results: List[Dict[str, Any]] = []
        for event in events:
            results.append(await self._handle_single_event(trigger, event))

        # Layer-3: advance the stored cursor so future pushes only fetch the
        # range past this one. Only move forward, never backward.
        await self._advance_cursor(trigger, provider, raw_payload)

        return {'status': 'ok', 'events': results}

    async def _advance_cursor(
        self,
        trigger: AgenticTrigger,
        provider: TriggerProvider,
        raw_payload: Dict[str, Any],
    ) -> None:
        incoming_cursor = provider.extract_push_cursor(raw_payload)
        if incoming_cursor is None:
            return
        current = await self._triggers.find_one(id=trigger.id)
        if not current:
            return
        config = dict(current.provider_config or {})
        stored = config.get('history_id')
        if stored is not None and int(incoming_cursor) <= int(stored):
            return
        config['history_id'] = int(incoming_cursor)
        await self._triggers.find_one_and_update(
            {'id': trigger.id}, provider_config=config
        )

    async def _handle_single_event(
        self, trigger: AgenticTrigger, event: NormalizedEmailEvent
    ) -> Dict[str, Any]:
        existing = await self._events.find_one(
            trigger_id=trigger.id, provider_event_id=event.provider_event_id
        )
        if existing:
            return {
                'provider_event_id': event.provider_event_id,
                'status': existing.status,
                'duplicate': True,
            }

        row = await self._events.create(
            trigger_id=trigger.id,
            provider_event_id=event.provider_event_id,
            status='received',
            subject=event.subject[:1024] if event.subject else None,
        )

        filter_config = trigger.filter_config or {}
        subject_regex = filter_config.get('subject_regex')
        if subject_regex and not re.search(subject_regex, event.subject or ''):
            await self._events.find_one_and_update(
                {'id': row.id},
                status='filtered_out',
                processed_at=datetime.now(timezone.utc),
            )
            return {
                'provider_event_id': event.provider_event_id,
                'status': 'filtered_out',
            }

        try:
            inputs = build_inference_inputs(
                event,
                allowed_mime_types=filter_config.get('allowed_mime_types'),
            )
            execution = await self._dispatch_inference(trigger, event, inputs)
            await self._events.find_one_and_update(
                {'id': row.id},
                status='dispatched',
                execution_id=execution.execution_id,
                processed_at=datetime.now(timezone.utc),
            )
            return {
                'provider_event_id': event.provider_event_id,
                'status': 'dispatched',
                'execution_id': str(execution.execution_id),
            }
        except EmailTooLargeError as exc:
            await self._events.find_one_and_update(
                {'id': row.id},
                status='failed',
                error=f'email_too_large: {exc}',
                processed_at=datetime.now(timezone.utc),
            )
            return {
                'provider_event_id': event.provider_event_id,
                'status': 'failed',
                'error': str(exc),
            }
        except Exception as exc:
            logger.exception(
                f'Failed to dispatch trigger event {event.provider_event_id}'
            )
            await self._events.find_one_and_update(
                {'id': row.id},
                status='failed',
                error=str(exc)[:2000],
                processed_at=datetime.now(timezone.utc),
            )
            return {
                'provider_event_id': event.provider_event_id,
                'status': 'failed',
                'error': str(exc),
            }

    async def _dispatch_inference(
        self,
        trigger: AgenticTrigger,
        event: NormalizedEmailEvent,
        inputs: List[Dict[str, Any]],
    ):
        variables = {
            'trigger_id': str(trigger.id),
            'trigger_name': trigger.name,
            'email_subject': event.subject or '',
            'email_from': event.sender or '',
        }

        if trigger.entity_type == 'agent':
            return await self._async_exec.create_and_enqueue_agent(
                agent_id=trigger.entity_id,
                inputs=inputs,
                variables=variables,
                output_json_enabled=True,
                access_token=None,
                app_key=None,
            )

        workflow = await self._workflows.find_one(id=trigger.entity_id)
        if not workflow:
            raise RuntimeError(f'Workflow {trigger.entity_id} not found')
        return await self._async_exec.create_and_enqueue_workflow(
            workflow_id=workflow.id,
            workflow_name=workflow.name,
            namespace=workflow.namespace,
            inputs=inputs,
            variables=variables,
            output_json_enabled=False,
            access_token=None,
            app_key=None,
        )

    async def _fresh_access_token(
        self, credential_id: UUID, provider: TriggerProvider
    ) -> tuple[str, str]:
        credential = await self._credentials.find_one(id=credential_id)
        if not credential:
            raise RuntimeError(f'Credential {credential_id} not found')

        now = datetime.now(timezone.utc)
        if (
            credential.encrypted_access_token
            and credential.token_expires_at
            and credential.token_expires_at > now
        ):
            return (
                self._crypto.decrypt(credential.encrypted_access_token) or '',
                credential.external_account_id,
            )

        refresh_token = self._crypto.decrypt(credential.encrypted_refresh_token)
        bundle = await provider.refresh_access_token(refresh_token or '')
        await self._credentials.find_one_and_update(
            {'id': credential_id},
            encrypted_access_token=self._crypto.encrypt(bundle.access_token),
            token_expires_at=bundle.expires_at,
        )
        return bundle.access_token or '', credential.external_account_id
