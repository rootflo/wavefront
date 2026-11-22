import uuid
from typing import Any, Optional

import yaml
from common_module.log.logger import logger
from db_repo_module.models.chatbot import Chatbot
from db_repo_module.models.namespace import Namespace
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from flo_ai.utils.variable_extractor import extract_variables_from_text
from sqlalchemy.exc import IntegrityError


class ChatbotNotFoundError(Exception):
    pass


class ChatbotValidationError(Exception):
    pass


class ChatbotService:
    """CRUD for chatbot definitions."""

    def __init__(
        self,
        chatbot_repository: SQLAlchemyRepository[Chatbot],
        namespace_repository: SQLAlchemyRepository[Namespace],
        llm_inference_config_service,
        agent_crud_service=None,
    ):
        self.chatbot_repository = chatbot_repository
        self.namespace_repository = namespace_repository
        self.llm_inference_config_service = llm_inference_config_service
        # Only needed to validate an agent-backed chatbot. Optional so entry
        # points that never create one do not have to build the agents stack.
        self.agent_crud_service = agent_crud_service

    async def _ensure_namespace(self, namespace: str) -> None:
        """Create the namespace on first use, mirroring how agents behave."""
        existing = await self.namespace_repository.find_one(name=namespace)
        if existing:
            return

        logger.info(f'Auto-creating namespace for chatbot: {namespace}')
        try:
            await self.namespace_repository.create(name=namespace)
        except IntegrityError:
            # Two creates racing on a brand-new namespace: the loser sees a
            # primary-key violation on namespaces.name. The namespace now
            # exists either way, which is all this method promised.
            logger.info(f'Namespace already created concurrently: {namespace}')

    async def _validate_llm_config(self, llm_config_id: uuid.UUID) -> None:
        # get_config already filters is_deleted, so a missing result covers both
        # "never existed" and "soft-deleted".
        config = await self.llm_inference_config_service.get_config(llm_config_id)
        if not config:
            raise ChatbotValidationError(
                f'LLM inference configuration not found: {llm_config_id}'
            )

    async def _validate_agent(
        self, agent_id: uuid.UUID, agent_version: Optional[int] = None
    ) -> None:
        """Check that the agent (and version, if pinned) exists and can chat."""
        if self.agent_crud_service is None:
            raise ChatbotValidationError(
                'Agent-backed chatbots are not available in this deployment'
            )

        try:
            agent = await self.agent_crud_service.get_agent(
                agent_id, version=agent_version
            )
        except ValueError as exc:
            # get_agent's message names the id and version, which the admin
            # making this request supplied.
            raise ChatbotValidationError(str(exc)) from exc

        # A chat session has nowhere to supply values for placeholders in the
        # agent's prompt, so the first message would fail on them. Refuse here,
        # where the admin can do something about it.
        try:
            definition = (yaml.safe_load(agent.get('yaml_content') or '') or {}).get(
                'agent'
            ) or {}
        except yaml.YAMLError as exc:
            raise ChatbotValidationError(
                f'Agent {agent_id} has an invalid definition: {exc}'
            ) from exc

        prompt = f"{definition.get('job') or ''}\n{definition.get('prompt') or ''}"
        variables = sorted(extract_variables_from_text(prompt))
        if variables:
            raise ChatbotValidationError(
                f'Agent {agent_id} cannot back a chatbot: its prompt needs '
                f'variables ({", ".join(variables)}) and a chat session cannot '
                'supply them'
            )

    async def create_chatbot(
        self,
        name: str,
        namespace: str,
        system_prompt: Optional[str] = None,
        llm_config_id: Optional[uuid.UUID] = None,
        description: Optional[str] = None,
        welcome_message: Optional[str] = None,
        config: Optional[dict[str, Any]] = None,
        enabled: bool = False,
        agent_id: Optional[uuid.UUID] = None,
        agent_version: Optional[int] = None,
    ) -> dict:
        # The payload model enforces the same split; repeated here because the
        # service is also the boundary for callers that do not go through it.
        if agent_id is not None:
            if system_prompt is not None or llm_config_id is not None:
                raise ChatbotValidationError(
                    'An agent-backed chatbot takes its prompt and model from the agent'
                )
            await self._validate_agent(agent_id, agent_version)
        else:
            if not system_prompt or llm_config_id is None:
                raise ChatbotValidationError(
                    'A chatbot needs either agent_id or both system_prompt and '
                    'llm_config_id'
                )
            await self._validate_llm_config(llm_config_id)
        await self._ensure_namespace(namespace)

        try:
            chatbot = await self.chatbot_repository.create(
                name=name,
                namespace=namespace,
                description=description,
                system_prompt=system_prompt,
                welcome_message=welcome_message,
                llm_config_id=llm_config_id,
                agent_id=agent_id,
                agent_version=agent_version,
                config=config,
                enabled=enabled,
            )
        except IntegrityError as exc:
            # The unique constraint is the authority on collisions; a
            # check-then-insert would race between two concurrent creates.
            raise ChatbotValidationError(
                f"A chatbot named '{name}' already exists in namespace '{namespace}'"
            ) from exc

        return chatbot.to_dict()

    async def get_chatbot(self, chatbot_id: uuid.UUID) -> Chatbot:
        chatbot = await self.chatbot_repository.find_one(
            id=chatbot_id, is_deleted=False
        )
        if not chatbot:
            raise ChatbotNotFoundError(f'Chatbot not found: {chatbot_id}')
        return chatbot

    async def list_chatbots(
        self,
        namespace: Optional[str] = None,
        enabled: Optional[bool] = None,
        limit: int = 100,
    ) -> list[dict]:
        filters: dict[str, Any] = {'is_deleted': False}
        if namespace is not None:
            filters['namespace'] = namespace
        if enabled is not None:
            filters['enabled'] = enabled

        chatbots = await self.chatbot_repository.find(
            limit=limit, order_by=('created_at', 'desc'), **filters
        )
        return [chatbot.to_dict() for chatbot in chatbots]

    async def update_chatbot(self, chatbot_id: uuid.UUID, **updates: Any) -> dict:
        # Callers strip unsupplied fields; an empty update would otherwise bump
        # updated_at for nothing.
        updates = {key: value for key, value in updates.items() if value is not None}

        chatbot = await self.get_chatbot(chatbot_id)
        if not updates:
            return chatbot.to_dict()

        # A chatbot keeps the kind it was created as. Switching would leave
        # sessions opened under the old kind pinned to something the chatbot no
        # longer is; make a new chatbot instead.
        if chatbot.agent_id is not None:
            if 'system_prompt' in updates or 'llm_config_id' in updates:
                raise ChatbotValidationError(
                    'This chatbot is agent-backed: system_prompt and '
                    'llm_config_id do not apply to it'
                )
            if 'agent_id' in updates or 'agent_version' in updates:
                await self._validate_agent(
                    updates.get('agent_id', chatbot.agent_id),
                    updates.get('agent_version', chatbot.agent_version),
                )
        elif 'agent_id' in updates or 'agent_version' in updates:
            raise ChatbotValidationError(
                'This chatbot is not agent-backed: agent_id and agent_version '
                'do not apply to it'
            )

        if 'llm_config_id' in updates:
            await self._validate_llm_config(updates['llm_config_id'])

        try:
            updated = await self.chatbot_repository.find_one_and_update(
                {'id': chatbot_id, 'is_deleted': False}, refresh=True, **updates
            )
        except IntegrityError as exc:
            raise ChatbotValidationError(
                f"A chatbot named '{updates.get('name')}' already exists in "
                f"namespace '{chatbot.namespace}'"
            ) from exc

        if not updated:
            raise ChatbotNotFoundError(f'Chatbot not found: {chatbot_id}')
        return updated.to_dict()

    async def delete_chatbot(self, chatbot_id: uuid.UUID) -> None:
        """Soft delete. Existing sessions keep their prompt snapshot and stay
        readable; they just cannot accept new messages.
        """
        updated = await self.chatbot_repository.find_one_and_update(
            {'id': chatbot_id, 'is_deleted': False}, is_deleted=True
        )
        if not updated:
            raise ChatbotNotFoundError(f'Chatbot not found: {chatbot_id}')
