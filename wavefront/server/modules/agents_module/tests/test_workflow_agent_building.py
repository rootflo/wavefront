"""
Tests for the shared agent-building path used by standalone agents and by both
kinds of workflow agent - referenced (`namespace/name`) and inline.

Workflow agents used to be built with a bare AgentBuilder.from_yaml(), which
skipped LlmInferenceConfig resolution (so DB-configured parameters like
temperature were silently ignored) and skipped the message-processor/API-service
tool fallbacks. Both services now delegate to
AgentInferenceService.create_agent_from_yaml, which resolves the config itself
whenever the caller does not supply one.

Inline agents needed the same treatment separately: they are never picked up by
extract_agent_references, so AriumBuilder built them itself, and it has no
database access with which to resolve a `provider: rootflo` model_id.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest
import yaml
from db_repo_module.models.llm_inference_config import LlmInferenceConfig

from agents_module.services.agent_inference_service import AgentInferenceService
from agents_module.services.workflow_inference_service import WorkflowInferenceService
from agents_module.utils.workflow_reference_utils import (
    extract_inline_agent_definitions,
)

CONFIG_ID = str(uuid4())

ROOTFLO_YAML = f"""
agent:
  name: test-agent
  job: Say hello
  model:
    provider: rootflo
    model_id: {CONFIG_ID}
    base_url: https://rootflo.example.invalid
"""

OPENAI_YAML = """
agent:
  name: test-agent
  job: Say hello
  model:
    provider: openai
    name: gpt-4.1-mini
"""


def stored_config(**overrides) -> dict:
    """A LlmInferenceConfig row as llm_inference_config_service.get_config returns it."""
    config = {
        'llm_model': 'gpt-4.1-mini',
        'display_name': 'Configured in DB',
        'api_key': 'test-key-123',
        'type': 'openai',
        'base_url': 'https://example.invalid',
        'parameters': {'temperature': 0.0, 'top_p': 0.5},
    }
    config.update(overrides)
    return config


@pytest.fixture
def agent_service() -> AgentInferenceService:
    """Skip the DI wiring; only the collaborators used here are populated."""
    service = object.__new__(AgentInferenceService)
    service.tool_loader = Mock(load_tool_with_name=Mock(return_value=None))
    service.message_processor_repository = AsyncMock(
        find_one=AsyncMock(return_value=None)
    )
    service.api_services_manager = None
    service.cloud_storage_manager = Mock()
    service.message_processor_bucket_name = 'test-bucket'
    service.llm_inference_config_service = AsyncMock(
        get_config=AsyncMock(return_value=stored_config())
    )
    return service


@pytest.fixture
def builder():
    """Patch AgentBuilder so no real LLM/provider client is constructed."""
    with patch(
        'agents_module.services.agent_inference_service.AgentBuilder'
    ) as agent_builder:
        instance = MagicMock()
        instance.with_llm.return_value = instance
        agent_builder.from_yaml.return_value = instance
        yield instance


class TestCreateAgentFromYamlResolvesConfig:
    """create_agent_from_yaml resolves the LLM config for every caller"""

    async def test_rootflo_yaml_is_resolved_when_no_config_passed(
        self, agent_service, builder
    ):
        """This is what workflow agents were missing entirely."""
        await agent_service.create_agent_from_yaml(ROOTFLO_YAML, 'test-agent')

        agent_service.llm_inference_config_service.get_config.assert_awaited_once()
        assert (
            str(agent_service.llm_inference_config_service.get_config.await_args[0][0])
            == CONFIG_ID
        )

        # The resolved row's parameters must reach the LLM that overrides the YAML one
        builder.with_llm.assert_called_once()
        llm = builder.with_llm.call_args[0][0]
        assert llm.temperature == 0.0
        assert llm.kwargs == {'top_p': 0.5}

    async def test_explicit_config_wins_without_a_lookup(self, agent_service, builder):
        """A caller-supplied override must not be second-guessed."""
        explicit = LlmInferenceConfig(**stored_config(parameters={'temperature': 0.9}))

        await agent_service.create_agent_from_yaml(ROOTFLO_YAML, 'test-agent', explicit)

        agent_service.llm_inference_config_service.get_config.assert_not_awaited()
        assert builder.with_llm.call_args[0][0].temperature == 0.9

    async def test_non_rootflo_yaml_is_left_alone(self, agent_service, builder):
        """A plain provider block stays owned by AgentBuilder.from_yaml."""
        await agent_service.create_agent_from_yaml(OPENAI_YAML, 'test-agent')

        agent_service.llm_inference_config_service.get_config.assert_not_awaited()
        builder.with_llm.assert_not_called()

    async def test_missing_config_service_is_reported(self, agent_service, builder):
        """Regression guard for containers that forget to wire the service.

        workflow_job/main.py did not pass llm_inference_config_service; without
        it, every rootflo agent inside a workflow fails to build.
        """
        agent_service.llm_inference_config_service = None

        with pytest.raises(ValueError, match='llm_inference_config_service'):
            await agent_service.create_agent_from_yaml(ROOTFLO_YAML, 'test-agent')


class TestBuildReferencedAgents:
    """WorkflowInferenceService delegates agent building to AgentInferenceService"""

    @pytest.fixture
    def workflow_service(self) -> WorkflowInferenceService:
        service = object.__new__(WorkflowInferenceService)
        service.agent_crud_service = AsyncMock(
            get_agent_yaml_from_bucket=AsyncMock(return_value=ROOTFLO_YAML)
        )
        service.agent_inference_service = AsyncMock(
            create_agent_from_yaml=AsyncMock(return_value=Mock(name='built-agent'))
        )
        return service

    async def test_each_reference_is_built_through_the_agent_service(
        self, workflow_service
    ):
        agents = await workflow_service._build_referenced_agents(
            ['ns/first', 'ns/second'], access_token='token', app_key='key'
        )

        assert set(agents) == {'ns/first', 'ns/second'}
        create = workflow_service.agent_inference_service.create_agent_from_yaml
        assert create.await_count == 2
        # access_token/app_key must survive the hand-off
        assert create.await_args.kwargs == {
            'access_token': 'token',
            'app_key': 'key',
        }

    async def test_versioned_reference_keeps_its_key_and_resolves_the_version(
        self, workflow_service
    ):
        """AriumBuilder matches node names on the full reference, '@version' included."""
        agents = await workflow_service._build_referenced_agents(['ns/first@3'])

        assert list(agents) == ['ns/first@3']
        assert (
            workflow_service.agent_crud_service.get_agent_yaml_from_bucket.await_args[1]
            == {'version': 3}
        )

    async def test_malformed_reference_is_skipped(self, workflow_service):
        agents = await workflow_service._build_referenced_agents(['no-namespace'])

        assert agents == {}
        workflow_service.agent_inference_service.create_agent_from_yaml.assert_not_awaited()

    async def test_build_failure_fails_the_whole_workflow(self, workflow_service):
        """A half-built workflow is worse than a clear error."""
        workflow_service.agent_inference_service.create_agent_from_yaml.side_effect = (
            ValueError('LLM inference configuration not found')
        )

        with pytest.raises(
            ValueError, match='Failed to build referenced agent ns/first'
        ):
            await workflow_service._build_referenced_agents(['ns/first'])


# The workflow shape that exposed the gap: agents written inline in the arium YAML
# rather than referenced as namespace/name.
INLINE_ARIUM = {
    'agents': [
        {
            'name': 'content_creator',
            'role': 'Content Creator',
            'job': 'Write a short draft on the given topic.',
            'model': {'model_id': CONFIG_ID, 'provider': 'rootflo'},
            'settings': {'temperature': 0.3},
        },
        {
            'name': 'editor',
            'role': 'Content Editor',
            'job': 'Polish the draft.',
            'model': {'model_id': CONFIG_ID, 'provider': 'rootflo'},
        },
    ]
}


class TestExtractInlineAgentDefinitions:
    """Only agents carrying their own config in the workflow YAML are collected"""

    def test_inline_agents_are_collected_in_order(self):
        found = extract_inline_agent_definitions(INLINE_ARIUM)

        assert [name for name, _ in found] == ['content_creator', 'editor']
        assert found[0][1]['settings'] == {'temperature': 0.3}

    def test_references_are_left_to_the_other_extractor(self):
        """A namespace/name entry is a reference, not an inline definition."""
        config = {'agents': [{'name': 'ns/stored-agent'}, {'name': 'ns/other@2'}]}

        assert extract_inline_agent_definitions(config) == []

    def test_name_only_entries_are_skipped(self):
        """A bare name refers to an agent the caller already built."""
        config = {'agents': [{'name': 'prebuilt'}]}

        assert extract_inline_agent_definitions(config) == []

    def test_yaml_config_entries_are_collected(self):
        config = {'agents': [{'name': 'from_yaml', 'yaml_config': 'agent:\n  name: x'}]}

        assert [name for name, _ in extract_inline_agent_definitions(config)] == [
            'from_yaml'
        ]

    def test_nested_ariums_are_walked_and_names_deduped(self):
        config = {
            'agents': [{'name': 'outer', 'job': 'a'}],
            'ariums': [
                {
                    'agents': [
                        {'name': 'inner', 'job': 'b'},
                        {'name': 'outer', 'job': 'duplicate'},
                    ]
                }
            ],
        }

        assert [name for name, _ in extract_inline_agent_definitions(config)] == [
            'outer',
            'inner',
        ]


class TestBuildInlineAgents:
    """Inline agents are built through the agent service, like referenced ones"""

    @pytest.fixture
    def workflow_service(self) -> WorkflowInferenceService:
        service = object.__new__(WorkflowInferenceService)
        service.agent_inference_service = AsyncMock(
            create_agent_from_yaml=AsyncMock(return_value=Mock(spec=['input_filter']))
        )
        return service

    async def test_definition_is_rewrapped_as_an_agent_document(self, workflow_service):
        """AgentBuilder expects a top-level `agent:` key."""
        await workflow_service._build_inline_agents(
            extract_inline_agent_definitions(INLINE_ARIUM)
        )

        create = workflow_service.agent_inference_service.create_agent_from_yaml
        assert create.await_count == 2

        first_yaml = yaml.safe_load(create.await_args_list[0][0][0])
        assert first_yaml['agent']['name'] == 'content_creator'
        assert first_yaml['agent']['model'] == {
            'model_id': CONFIG_ID,
            'provider': 'rootflo',
        }
        # settings must survive: it is the highest-precedence temperature source
        assert first_yaml['agent']['settings'] == {'temperature': 0.3}

    async def test_agents_are_keyed_by_their_workflow_name(self, workflow_service):
        """AriumBuilder matches these against the node names in the arium graph."""
        agents = await workflow_service._build_inline_agents(
            extract_inline_agent_definitions(INLINE_ARIUM)
        )

        assert set(agents) == {'content_creator', 'editor'}

    async def test_input_filter_is_reapplied(self, workflow_service):
        """AriumBuilder only applies this on the path we bypass."""
        agents = await workflow_service._build_inline_agents(
            [('summariser', {'name': 'summariser', 'job': 'x', 'input_filter': ['a']})]
        )

        assert agents['summariser'].input_filter == ['a']

    async def test_arium_only_keys_are_stripped(self, workflow_service):
        """input_filter is not part of an agent YAML schema."""
        await workflow_service._build_inline_agents(
            [('summariser', {'name': 'summariser', 'job': 'x', 'input_filter': ['a']})]
        )

        create = workflow_service.agent_inference_service.create_agent_from_yaml
        assert 'input_filter' not in yaml.safe_load(create.await_args[0][0])['agent']

    async def test_yaml_config_is_passed_through_verbatim(self, workflow_service):
        """It is already an agent document, so re-wrapping would double-nest it."""
        agent_yaml = 'agent:\n  name: inlined\n  job: do a thing\n'

        await workflow_service._build_inline_agents(
            [('inlined', {'name': 'inlined', 'yaml_config': agent_yaml})]
        )

        create = workflow_service.agent_inference_service.create_agent_from_yaml
        assert create.await_args[0][0] == agent_yaml

    async def test_build_failure_fails_the_whole_workflow(self, workflow_service):
        workflow_service.agent_inference_service.create_agent_from_yaml.side_effect = (
            ValueError('LLM inference configuration not found')
        )

        with pytest.raises(ValueError, match='Failed to build inline agent editor'):
            await workflow_service._build_inline_agents(
                [('editor', {'name': 'editor', 'job': 'x'})]
            )
