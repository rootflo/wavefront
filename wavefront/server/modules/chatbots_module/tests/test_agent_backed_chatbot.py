"""Creating and updating a chatbot that is backed by an agent, and opening a
session against one."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from db_repo_module.models.chat_session import ChatSession
from db_repo_module.models.chatbot import Chatbot
from pydantic import ValidationError

from chatbots_module.models.chatbot_schemas import (
    CreateChatbotPayload,
    UpdateChatbotPayload,
)
from chatbots_module.services.chat_session_service import ChatSessionService
from chatbots_module.services.chatbot_service import (
    ChatbotService,
    ChatbotValidationError,
)

from fakes import FakeDbSession, repository_with_session

AGENT_YAML = """
agent:
  name: support
  job: You help customers with their orders.
"""


def _agent_crud(yaml_content=AGENT_YAML, error=None):
    crud = AsyncMock()
    if error is not None:
        crud.get_agent.side_effect = error
    else:
        crud.get_agent.return_value = {'yaml_content': yaml_content, 'version': 4}
    return crud


def _service(chatbot_repo=None, agent_crud=None, llm_configs=None):
    return ChatbotService(
        chatbot_repository=chatbot_repo or AsyncMock(),
        namespace_repository=AsyncMock(),
        llm_inference_config_service=llm_configs or AsyncMock(),
        agent_crud_service=agent_crud,
    )


class TestCreatePayload:
    def test_prompt_based(self):
        payload = CreateChatbotPayload(
            name='bot', system_prompt='Be helpful.', llm_config_id=uuid.uuid4()
        )
        assert payload.agent_id is None

    def test_agent_backed(self):
        agent_id = uuid.uuid4()
        payload = CreateChatbotPayload(name='bot', agent_id=agent_id, agent_version=2)

        assert payload.agent_id == agent_id
        assert payload.system_prompt is None
        assert payload.llm_config_id is None

    @pytest.mark.parametrize(
        'fields',
        [
            {},
            {'system_prompt': 'Be helpful.'},
            {'llm_config_id': uuid.uuid4()},
            {'system_prompt': '   ', 'llm_config_id': uuid.uuid4()},
            {'agent_version': 2, 'system_prompt': 'x', 'llm_config_id': uuid.uuid4()},
        ],
    )
    def test_a_prompt_based_chatbot_needs_its_prompt_and_model(self, fields):
        with pytest.raises(ValidationError):
            CreateChatbotPayload(name='bot', **fields)

    @pytest.mark.parametrize(
        'fields',
        [
            {'system_prompt': 'Be helpful.'},
            {'llm_config_id': uuid.uuid4()},
        ],
    )
    def test_an_agent_backed_chatbot_cannot_also_have_its_own(self, fields):
        with pytest.raises(ValidationError):
            CreateChatbotPayload(name='bot', agent_id=uuid.uuid4(), **fields)

    def test_agent_version_must_be_positive(self):
        with pytest.raises(ValidationError):
            CreateChatbotPayload(name='bot', agent_id=uuid.uuid4(), agent_version=0)


class TestCreateAgentBacked:
    async def test_stores_the_agent_reference_and_no_prompt_or_model(self):
        repo = AsyncMock()
        repo.create.return_value = SimpleNamespace(to_dict=lambda: {'ok': True})
        crud = _agent_crud()
        llm_configs = AsyncMock()
        agent_id = uuid.uuid4()

        await _service(repo, crud, llm_configs).create_chatbot(
            name='bot', namespace='default', agent_id=agent_id, agent_version=4
        )

        crud.get_agent.assert_awaited_once_with(agent_id, version=4)
        created = repo.create.await_args.kwargs
        assert created['agent_id'] == agent_id
        assert created['agent_version'] == 4
        assert created['system_prompt'] is None
        assert created['llm_config_id'] is None
        llm_configs.get_config.assert_not_awaited()

    async def test_an_unknown_agent_is_rejected(self):
        crud = _agent_crud(error=ValueError('Agent not found with ID: x'))

        with pytest.raises(ChatbotValidationError, match='Agent not found'):
            await _service(agent_crud=crud).create_chatbot(
                name='bot', namespace='default', agent_id=uuid.uuid4()
            )

    async def test_an_agent_whose_prompt_needs_variables_is_rejected(self):
        crud = _agent_crud(
            'agent:\n  name: support\n  job: You help <customer_name> in <language>.\n'
        )
        repo = AsyncMock()

        with pytest.raises(ChatbotValidationError) as raised:
            await _service(repo, crud).create_chatbot(
                name='bot', namespace='default', agent_id=uuid.uuid4()
            )

        assert 'customer_name' in str(raised.value)
        assert 'language' in str(raised.value)
        repo.create.assert_not_awaited()

    async def test_not_available_without_the_agents_stack(self):
        with pytest.raises(ChatbotValidationError, match='not available'):
            await _service(agent_crud=None).create_chatbot(
                name='bot', namespace='default', agent_id=uuid.uuid4()
            )

    async def test_a_mix_of_both_kinds_is_rejected(self):
        with pytest.raises(ChatbotValidationError):
            await _service(agent_crud=_agent_crud()).create_chatbot(
                name='bot',
                namespace='default',
                agent_id=uuid.uuid4(),
                system_prompt='Be helpful.',
            )

    async def test_a_prompt_based_chatbot_is_created_as_before(self):
        repo = AsyncMock()
        repo.create.return_value = SimpleNamespace(to_dict=lambda: {'ok': True})
        llm_configs = AsyncMock()
        llm_configs.get_config.return_value = {'id': 'x'}
        llm_config_id = uuid.uuid4()

        await _service(repo, llm_configs=llm_configs).create_chatbot(
            name='bot',
            namespace='default',
            system_prompt='Be helpful.',
            llm_config_id=llm_config_id,
        )

        created = repo.create.await_args.kwargs
        assert created['system_prompt'] == 'Be helpful.'
        assert created['llm_config_id'] == llm_config_id
        assert created['agent_id'] is None


class TestUpdate:
    def _repo(self, chatbot):
        repo = AsyncMock()
        repo.find_one.return_value = chatbot
        repo.find_one_and_update.return_value = SimpleNamespace(to_dict=lambda: {})
        return repo

    def test_update_payload_accepts_agent_fields(self):
        payload = UpdateChatbotPayload(agent_version=3)
        assert payload.agent_version == 3

    async def test_an_agent_backed_chatbot_can_move_to_another_version(self):
        agent_id = uuid.uuid4()
        chatbot = SimpleNamespace(
            agent_id=agent_id, agent_version=1, namespace='default', to_dict=dict
        )
        repo = self._repo(chatbot)
        crud = _agent_crud()

        await _service(repo, crud).update_chatbot(uuid.uuid4(), agent_version=2)

        crud.get_agent.assert_awaited_once_with(agent_id, version=2)
        assert repo.find_one_and_update.await_args.kwargs['agent_version'] == 2

    async def test_an_agent_backed_chatbot_cannot_be_given_a_prompt(self):
        chatbot = SimpleNamespace(
            agent_id=uuid.uuid4(), agent_version=None, namespace='default'
        )
        repo = self._repo(chatbot)

        with pytest.raises(ChatbotValidationError, match='agent-backed'):
            await _service(repo, _agent_crud()).update_chatbot(
                uuid.uuid4(), system_prompt='Be helpful.'
            )
        repo.find_one_and_update.assert_not_awaited()

    async def test_a_prompt_based_chatbot_cannot_be_given_an_agent(self):
        chatbot = SimpleNamespace(
            agent_id=None, agent_version=None, namespace='default'
        )
        repo = self._repo(chatbot)

        with pytest.raises(ChatbotValidationError, match='not agent-backed'):
            await _service(repo, _agent_crud()).update_chatbot(
                uuid.uuid4(), agent_id=uuid.uuid4()
            )
        repo.find_one_and_update.assert_not_awaited()

    async def test_other_fields_of_an_agent_backed_chatbot_can_change(self):
        chatbot = SimpleNamespace(
            agent_id=uuid.uuid4(), agent_version=None, namespace='default'
        )
        repo = self._repo(chatbot)
        crud = _agent_crud()

        await _service(repo, crud).update_chatbot(uuid.uuid4(), enabled=True)

        crud.get_agent.assert_not_awaited()
        assert repo.find_one_and_update.await_args.kwargs == {
            'refresh': True,
            'enabled': True,
        }


class TestChatbotRow:
    def _chatbot(self, **fields):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        return Chatbot(
            id=uuid.uuid4(),
            namespace='default',
            name='bot',
            enabled=True,
            is_deleted=False,
            created_at=now,
            updated_at=now,
            **fields,
        )

    def test_agent_backed_row_serialises_without_a_model(self):
        agent_id = uuid.uuid4()
        payload = self._chatbot(agent_id=agent_id, agent_version=2).to_dict()

        assert payload['agent_id'] == str(agent_id)
        assert payload['agent_version'] == 2
        assert payload['llm_config_id'] is None
        assert payload['system_prompt'] is None

    def test_prompt_based_row_is_unchanged_apart_from_the_new_keys(self):
        llm_config_id = uuid.uuid4()
        payload = self._chatbot(
            system_prompt='Be helpful.', llm_config_id=llm_config_id
        ).to_dict()

        assert payload['llm_config_id'] == str(llm_config_id)
        assert payload['system_prompt'] == 'Be helpful.'
        assert payload['agent_id'] is None
        assert payload['agent_version'] is None


class TestSessionPin:
    async def test_an_agent_session_records_its_agent_and_no_prompt(self):
        db_session = FakeDbSession()
        service = ChatSessionService(
            chat_session_repository=repository_with_session(db_session),
            chat_message_repository=AsyncMock(),
        )
        chatbot = SimpleNamespace(
            id=uuid.uuid4(), system_prompt=None, welcome_message=None
        )
        pin = {'agent_id': str(uuid.uuid4()), 'agent_version': 4}

        await service.create_session(chatbot, uuid.uuid4(), metadata=pin)

        (session,) = db_session.added_of(ChatSession)
        assert session.metadata_ == pin
        assert session.system_prompt_snapshot == ''

    async def test_a_prompt_based_session_is_created_as_before(self):
        db_session = FakeDbSession()
        service = ChatSessionService(
            chat_session_repository=repository_with_session(db_session),
            chat_message_repository=AsyncMock(),
        )
        chatbot = SimpleNamespace(
            id=uuid.uuid4(), system_prompt='Be helpful.', welcome_message=None
        )

        await service.create_session(chatbot, uuid.uuid4())

        (session,) = db_session.added_of(ChatSession)
        assert session.system_prompt_snapshot == 'Be helpful.'
        assert session.metadata_ is None
