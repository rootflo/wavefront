"""
Tests for the ':validate' endpoints and the static YAML validation behind them.

Validation never builds an LLM or touches the network: documents are checked with
flo_ai's pydantic models plus the graph rules AriumBuilder enforces, and anything
that needs I/O (stored agents, subworkflows, tools) goes through collaborators that
are faked here. A document with problems answers 200 with ``valid: false``.

The controllers are called directly with their dependencies passed in, which skips
the DI wiring the same way the other service tests in this package do.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from common_module.response_formatter import ResponseFormatter

from agents_module.controllers.agent_controller import validate_agent
from agents_module.controllers.workflow_controller import validate_workflow
from agents_module.services.agent_crud_service import AgentCrudService
from agents_module.services.workflow_crud_service import WorkflowCrudService
from agents_module.utils.yaml_validation import (
    parse_yaml_document,
    validate_agent_document,
    validate_arium_document,
)

VALID_AGENT_YAML = """
agent:
  name: test-agent
  job: Say hello
  model:
    provider: openai
    name: gpt-4.1-mini
"""

MODEL = """
      model:
        provider: openai
        name: gpt-4.1-mini
"""

VALID_WORKFLOW_YAML = f"""
arium:
  agents:
    - name: writer
      job: Write a draft
{MODEL}
    - name: editor
      job: Edit the draft
{MODEL}
  workflow:
    start: writer
    edges:
      - from: writer
        to: [editor]
    end: [editor]
"""

ROUTED_WORKFLOW_YAML = f"""
arium:
  agents:
    - name: writer
      job: Write a draft
{MODEL}
    - name: editor
      job: Edit the draft
{MODEL}
    - name: reviewer
      job: Review the draft
{MODEL}
  routers:
    - name: pick
      type: smart
      routing_options:
        editor: Needs edits
        reviewer: Ready for review
  workflow:
    start: writer
    edges:
      - from: writer
        to: [editor, reviewer]
        router: pick
    end: [editor, reviewer]
"""


FUNCTION_WORKFLOW_YAML = VALID_WORKFLOW_YAML.replace(
    '  workflow:',
    """  function_nodes:
    - name: tidy
      function_name: not_registered
  workflow:""",
).replace(
    '    end: [editor]',
    '      - from: editor\n        to: [tidy]\n    end: [tidy]',
)


def error_pairs(report):
    return [(error.path, error.message) for error in report.errors]


def paths(report):
    return [error.path for error in report.errors]


def arium_report(yaml_text, **kwargs):
    data, errors = parse_yaml_document(yaml_text)
    assert errors == []
    return validate_arium_document(data, **kwargs)


class TestParseYamlDocument:
    def test_mapping_is_returned(self):
        data, errors = parse_yaml_document('agent:\n  name: a\n')
        assert data == {'agent': {'name': 'a'}}
        assert errors == []

    @pytest.mark.parametrize('text', ['', '   \n'])
    def test_empty_is_reported(self, text):
        data, errors = parse_yaml_document(text)
        assert data is None
        assert errors[0].message == 'YAML is empty'

    def test_malformed_yaml_is_reported_with_position(self):
        data, errors = parse_yaml_document('agent: [unclosed\n')
        assert data is None
        assert errors[0].path == ''
        assert errors[0].message.startswith('Invalid YAML')
        assert 'line' in errors[0].message

    def test_non_mapping_root_is_reported(self):
        data, errors = parse_yaml_document('- a\n- b\n')
        assert data is None
        assert 'mapping' in errors[0].message

    def test_python_tags_are_not_executed(self):
        """safe_load must reject object construction rather than run it."""
        data, errors = parse_yaml_document(
            'agent: !!python/object/apply:os.system ["echo hi"]\n'
        )
        assert data is None
        assert errors[0].message.startswith('Invalid YAML')


class TestValidateAgentDocument:
    def parse(self, text):
        data, errors = parse_yaml_document(text)
        assert errors == []
        return data

    def test_valid_agent(self):
        report = validate_agent_document(self.parse(VALID_AGENT_YAML))
        assert report.errors == []
        assert report.schema_valid

    def test_missing_job_is_a_schema_error(self):
        report = validate_agent_document(
            self.parse(
                """
agent:
  name: test-agent
  model:
    provider: openai
    name: gpt-4.1-mini
"""
            )
        )
        assert not report.schema_valid
        assert report.errors
        assert any('job' in message for _, message in error_pairs(report))

    def test_model_error_names_the_offending_key(self):
        report = validate_agent_document(
            self.parse(
                """
agent:
  name: test-agent
  job: Say hello
  model:
    provider: not-a-provider
    name: gpt-4.1-mini
"""
            )
        )
        assert not report.schema_valid
        assert 'agent.model.provider' in paths(report)

    def test_missing_model_is_rejected(self):
        """The server supplies no default LLM."""
        report = validate_agent_document(
            self.parse(
                """
agent:
  name: test-agent
  job: Say hello
"""
            )
        )
        assert 'agent.model' in paths(report)

    def test_rootflo_without_model_id_is_rejected(self):
        report = validate_agent_document(
            self.parse(
                """
agent:
  name: test-agent
  job: Say hello
  model:
    provider: rootflo
"""
            )
        )
        assert any('model_id' in message for _, message in error_pairs(report))

    def test_tools_are_collected_for_the_caller_to_resolve(self):
        report = validate_agent_document(
            self.parse(VALID_AGENT_YAML + '  tools:\n    - name: search\n')
        )
        assert report.errors == []
        assert [(ref.path, ref.name) for ref in report.tool_refs] == [
            ('agent.tools[0].name', 'search')
        ]

    def test_plain_tool_name_is_rejected(self):
        report = validate_agent_document(
            self.parse(VALID_AGENT_YAML + '  tools:\n    - search\n')
        )
        assert 'agent.tools[0]' in paths(report)


class TestValidateAriumDocument:
    def test_valid_workflow(self):
        report = arium_report(VALID_WORKFLOW_YAML)
        assert report.errors == []
        assert report.schema_valid

    def test_valid_routed_workflow(self):
        assert arium_report(ROUTED_WORKFLOW_YAML).errors == []

    def test_schema_error_stops_before_graph_rules(self):
        report = arium_report(
            """
arium:
  agents:
    - name: writer
      job: Write a draft
  workflow:
    start: writer
"""
        )
        assert not report.schema_valid
        assert 'arium.workflow.edges' in paths(report)

    def test_no_nodes_is_a_schema_error(self):
        report = arium_report(
            """
arium:
  workflow:
    start: a
    edges: []
    end: [a]
"""
        )
        assert not report.schema_valid
        assert any('at least one of' in message for _, message in error_pairs(report))

    def test_dangling_edge_target(self):
        report = arium_report(
            VALID_WORKFLOW_YAML.replace('to: [editor]', 'to: [ghost]')
        )
        assert 'arium.workflow.edges[0].to[0]' in paths(report)
        message = dict(error_pairs(report))['arium.workflow.edges[0].to[0]']
        assert "'ghost'" in message
        assert 'writer' in message  # lists what is available

    def test_dangling_edge_source(self):
        report = arium_report(
            VALID_WORKFLOW_YAML.replace('from: writer', 'from: ghost')
        )
        assert 'arium.workflow.edges[0].from' in paths(report)

    def test_unknown_start_node(self):
        report = arium_report(VALID_WORKFLOW_YAML.replace('start: writer', 'start: x'))
        assert 'arium.workflow.start' in paths(report)

    def test_unknown_end_node(self):
        report = arium_report(
            VALID_WORKFLOW_YAML.replace('end: [editor]', 'end: [ghost]')
        )
        assert 'arium.workflow.end[0]' in paths(report)

    def test_empty_end_is_rejected(self):
        report = arium_report(VALID_WORKFLOW_YAML.replace('end: [editor]', 'end: []'))
        assert 'arium.workflow.end' in paths(report)

    def test_duplicate_node_name(self):
        report = arium_report(
            VALID_WORKFLOW_YAML.replace('name: editor', 'name: writer')
        )
        assert 'arium.agents[1].name' in paths(report)

    def test_end_is_a_reserved_node_name(self):
        report = arium_report(VALID_WORKFLOW_YAML.replace('name: editor', 'name: end'))
        assert 'arium.agents[1].name' in paths(report)

    def test_end_as_edge_target_is_not_a_dangling_node(self):
        report = arium_report(
            VALID_WORKFLOW_YAML.replace(
                '    end: [editor]',
                '      - from: editor\n        to: [end]\n    end: [editor]',
            )
        )
        assert report.errors == []

    def test_multiple_targets_without_a_router(self):
        report = arium_report(
            ROUTED_WORKFLOW_YAML.replace('        router: pick\n', '')
        )
        assert 'arium.workflow.edges[0].to' in paths(report)

    def test_unknown_router(self):
        report = arium_report(
            ROUTED_WORKFLOW_YAML.replace('router: pick', 'router: nope')
        )
        assert 'arium.workflow.edges[0].router' in paths(report)

    def test_router_must_match_edge_targets(self):
        report = arium_report(
            ROUTED_WORKFLOW_YAML.replace('to: [editor, reviewer]', 'to: [editor]')
        )
        assert 'arium.workflow.edges[0].to' in paths(report)

    def test_router_option_missing_from_edge(self):
        report = arium_report(
            ROUTED_WORKFLOW_YAML.replace(
                '        reviewer: Ready for review\n',
                '        reviewer: Ready for review\n        writer: Start over\n',
            )
        )
        assert 'arium.workflow.edges[0].to' in paths(report)

    def test_smart_router_without_options_is_a_schema_error(self):
        report = arium_report(
            ROUTED_WORKFLOW_YAML.replace(
                """      routing_options:
        editor: Needs edits
        reviewer: Ready for review
""",
                '',
            )
        )
        assert not report.schema_valid
        assert any('routing_options' in message for _, message in error_pairs(report))

    def test_duplicate_router_name(self):
        report = arium_report(
            ROUTED_WORKFLOW_YAML.replace(
                '  workflow:',
                """    - name: pick
      type: field_match
      field: route
      routes:
        a: editor
  workflow:""",
            )
        )
        assert 'arium.routers[1].name' in paths(report)

    def test_field_match_router_targets_include_default(self):
        yaml_text = ROUTED_WORKFLOW_YAML.replace(
            """    - name: pick
      type: smart
      routing_options:
        editor: Needs edits
        reviewer: Ready for review
""",
            """    - name: pick
      type: field_match
      field: verdict
      routes:
        edit: editor
      default: reviewer
""",
        )
        assert arium_report(yaml_text).errors == []

    def test_second_outgoing_edge_from_a_node(self):
        report = arium_report(
            VALID_WORKFLOW_YAML.replace(
                '    end: [editor]',
                '      - from: writer\n        to: [editor]\n    end: [editor]',
            )
        )
        assert 'arium.workflow.edges[1].from' in paths(report)

    def test_end_node_with_outgoing_edge(self):
        report = arium_report(
            VALID_WORKFLOW_YAML.replace('end: [editor]', 'end: [writer, editor]')
        )
        assert 'arium.workflow.end[0]' in paths(report)

    def test_orphan_node(self):
        report = arium_report(
            VALID_WORKFLOW_YAML.replace(
                '  workflow:',
                f"""    - name: lonely
      job: Do nothing
{MODEL}
  workflow:""",
            )
        )
        assert 'arium.agents[2].name' in paths(report)

    def test_iterator_must_execute_a_known_node(self):
        report = arium_report(
            VALID_WORKFLOW_YAML.replace(
                '  workflow:',
                """  iterators:
    - name: each
      execute_node: ghost
  workflow:""",
            ).replace('to: [editor]', 'to: [each]')
        )
        assert 'arium.iterators[0].execute_node' in paths(report)

    def test_unknown_function_is_reported_when_a_registry_is_given(self):
        assert arium_report(FUNCTION_WORKFLOW_YAML).errors == []
        report = arium_report(FUNCTION_WORKFLOW_YAML, function_names={'passthrough'})
        assert 'arium.function_nodes[0].function_name' in paths(report)

    def test_yaml_file_agents_are_rejected(self):
        report = arium_report(
            """
arium:
  agents:
    - name: writer
      yaml_file: ./writer.yaml
  workflow:
    start: writer
    edges:
      - from: writer
        to: [end]
    end: [writer]
"""
        )
        assert 'arium.agents[0].yaml_file' in paths(report)

    def test_rootflo_agent_model_id_must_be_a_uuid(self):
        report = arium_report(
            VALID_WORKFLOW_YAML.replace(
                'provider: openai\n        name: gpt-4.1-mini',
                'provider: rootflo\n        model_id: not-a-uuid',
                1,
            )
        )
        assert 'arium.agents[0].model.model_id' in paths(report)

    def test_agent_reference_is_collected_for_the_caller_to_resolve(self):
        report = arium_report(
            f"""
arium:
  agents:
    - name: writer
      job: Write a draft
{MODEL}
    - name: shared/editor@2
  workflow:
    start: writer
    edges:
      - from: writer
        to: [shared/editor@2]
    end: [shared/editor@2]
"""
        )
        assert report.errors == []
        assert [(ref.path, ref.reference) for ref in report.agent_refs] == [
            ('arium.agents[1].name', 'shared/editor@2')
        ]

    def test_bare_name_without_configuration_is_rejected(self):
        report = arium_report(
            VALID_WORKFLOW_YAML.replace(
                f"""    - name: editor
      job: Edit the draft
{MODEL}""",
                '    - name: editor\n',
            )
        )
        assert 'arium.agents[1].name' in paths(report)

    def test_nested_arium_is_validated_against_its_own_nodes(self):
        report = arium_report(
            f"""
arium:
  agents:
    - name: writer
      job: Write a draft
{MODEL}
  ariums:
    - name: inner
      agents:
        - name: helper
          job: Help
          model: {{provider: openai, name: gpt-4.1-mini}}
      workflow:
        start: helper
        edges:
          - from: helper
            to: [writer]
        end: [helper]
  workflow:
    start: writer
    edges:
      - from: writer
        to: [inner]
    end: [inner]
"""
        )
        assert 'arium.ariums[0].workflow.edges[0].to[0]' in paths(report)


class FakeRequest:
    def __init__(self, body):
        self.body = AsyncMock(return_value=body)


def decode(response):
    return json.loads(response.body)


@pytest.fixture
def formatter():
    return ResponseFormatter()


@pytest.fixture
def agent_service():
    """Skip the DI wiring; tool lookups beyond the available tools find nothing."""
    service = object.__new__(AgentCrudService)
    service._try_load_message_processor_tool = AsyncMock(return_value=None)
    service._try_load_api_service_tool = AsyncMock(return_value=None)
    return service


@pytest.fixture
def workflow_service():
    service = object.__new__(WorkflowCrudService)
    service.tool_loader = Mock(
        function_node_registry={'passthrough': Mock()},
        load_all_tools=Mock(return_value=[]),
    )
    service.agent_crud_service = Mock(
        get_agent_yaml_from_bucket=AsyncMock(return_value=VALID_AGENT_YAML),
        resolve_tool=AsyncMock(return_value=None),
    )
    service.get_workflow_yaml_from_bucket = AsyncMock(
        side_effect=ValueError('Workflow not found: shared/missing')
    )
    return service


def tool(name):
    return SimpleNamespace(name=name)


class TestValidateAgentEndpoint:
    async def call(self, body, agent_service, formatter, tools=()):
        tool_loader = Mock(load_all_tools=Mock(return_value=list(tools)))
        response = await validate_agent(
            request=FakeRequest(body),
            agent_crud_service=agent_service,
            response_formatter=formatter,
            tool_loader=tool_loader,
        )
        assert response.status_code == 200
        payload = decode(response)
        assert payload['meta']['status'] == 'success'
        return payload['data']['data']

    async def test_valid_yaml(self, agent_service, formatter):
        result = await self.call(VALID_AGENT_YAML.encode(), agent_service, formatter)
        assert result == {'valid': True, 'errors': []}

    async def test_schema_error_is_a_200_with_paths(self, agent_service, formatter):
        body = VALID_AGENT_YAML.replace('provider: openai', 'provider: nope')
        result = await self.call(body.encode(), agent_service, formatter)
        assert result['valid'] is False
        assert 'agent.model.provider' in [e['path'] for e in result['errors']]
        assert all(set(e) == {'path', 'message'} for e in result['errors'])

    async def test_malformed_yaml_is_a_200(self, agent_service, formatter):
        result = await self.call(b'agent: [unclosed', agent_service, formatter)
        assert result['valid'] is False
        assert result['errors'][0]['path'] == ''

    async def test_non_utf8_body_is_a_200(self, agent_service, formatter):
        result = await self.call(b'\xff\xfe\x00', agent_service, formatter)
        assert result['valid'] is False
        assert 'UTF-8' in result['errors'][0]['message']

    async def test_unknown_tool_is_reported(self, agent_service, formatter):
        body = VALID_AGENT_YAML + '  tools:\n    - name: ghost\n'
        result = await self.call(body.encode(), agent_service, formatter)
        assert result['valid'] is False
        assert result['errors'][0]['path'] == 'agent.tools[0].name'
        assert 'ghost' in result['errors'][0]['message']

    async def test_available_tool_is_accepted(self, agent_service, formatter):
        body = VALID_AGENT_YAML + '  tools:\n    - name: search\n'
        result = await self.call(
            body.encode(), agent_service, formatter, tools=[tool('search')]
        )
        assert result['valid'] is True

    async def test_no_llm_is_built(self, agent_service, formatter):
        with patch('agents_module.services.agent_crud_service.AgentBuilder') as builder:
            await self.call(VALID_AGENT_YAML.encode(), agent_service, formatter)
        builder.from_yaml.assert_not_called()


class TestAgentCreateUsesTheSameValidation:
    async def test_invalid_agent_is_rejected_before_any_build(self, agent_service):
        body = VALID_AGENT_YAML.replace('provider: openai', 'provider: nope')
        with patch('agents_module.services.agent_crud_service.AgentBuilder') as builder:
            with pytest.raises(ValueError, match='Invalid agent YAML configuration'):
                await agent_service._validate_yaml_content(
                    body, 'default', 'test-agent', tool_available=[]
                )
        builder.from_yaml.assert_not_called()

    async def test_unknown_tool_is_rejected(self, agent_service):
        body = VALID_AGENT_YAML + '  tools:\n    - name: ghost\n'
        with patch('agents_module.services.agent_crud_service.AgentBuilder'):
            with pytest.raises(ValueError, match="Tool 'ghost' not found"):
                await agent_service._validate_yaml_content(
                    body, 'default', 'test-agent', tool_available=[]
                )

    async def test_valid_agent_is_built_with_its_resolved_tools(self, agent_service):
        body = VALID_AGENT_YAML + '  tools:\n    - name: search\n'
        search = tool('search')
        with patch('agents_module.services.agent_crud_service.AgentBuilder') as builder:
            await agent_service._validate_yaml_content(
                body, 'default', 'test-agent', tool_available=[search]
            )
        assert builder.from_yaml.call_args.kwargs['tool_registry'] == {'search': search}


class TestValidateWorkflowEndpoint:
    async def call(self, body, workflow_service, formatter):
        response = await validate_workflow(
            request=FakeRequest(body),
            workflow_crud_service=workflow_service,
            response_formatter=formatter,
        )
        assert response.status_code == 200
        payload = decode(response)
        assert payload['meta']['status'] == 'success'
        return payload['data']['data']

    async def test_valid_yaml(self, workflow_service, formatter):
        result = await self.call(
            VALID_WORKFLOW_YAML.encode(), workflow_service, formatter
        )
        assert result == {'valid': True, 'errors': []}

    async def test_schema_error(self, workflow_service, formatter):
        body = VALID_WORKFLOW_YAML.replace('provider: openai', 'provider: nope', 1)
        result = await self.call(body.encode(), workflow_service, formatter)
        assert result['valid'] is False
        assert 'arium.agents[0].model.provider' in [e['path'] for e in result['errors']]

    async def test_dangling_edge(self, workflow_service, formatter):
        body = VALID_WORKFLOW_YAML.replace('to: [editor]', 'to: [ghost]')
        result = await self.call(body.encode(), workflow_service, formatter)
        assert result['valid'] is False
        assert 'arium.workflow.edges[0].to[0]' in [e['path'] for e in result['errors']]

    async def test_bad_router(self, workflow_service, formatter):
        body = ROUTED_WORKFLOW_YAML.replace('router: pick', 'router: nope')
        result = await self.call(body.encode(), workflow_service, formatter)
        assert result['valid'] is False
        assert 'arium.workflow.edges[0].router' in [e['path'] for e in result['errors']]

    async def test_malformed_yaml(self, workflow_service, formatter):
        result = await self.call(b'arium: [unclosed', workflow_service, formatter)
        assert result['valid'] is False
        assert result['errors'][0]['path'] == ''

    async def test_missing_arium_root(self, workflow_service, formatter):
        result = await self.call(b'agent:\n  name: a\n', workflow_service, formatter)
        assert result['valid'] is False
        assert 'arium' in [e['path'] for e in result['errors']]

    async def test_non_utf8_body(self, workflow_service, formatter):
        result = await self.call(b'\xff\xfe\x00', workflow_service, formatter)
        assert result['valid'] is False

    async def test_missing_stored_agent_is_reported(self, workflow_service, formatter):
        workflow_service.agent_crud_service.get_agent_yaml_from_bucket = AsyncMock(
            side_effect=ValueError('Agent not found: shared/editor')
        )
        body = f"""
arium:
  agents:
    - name: writer
      job: Write a draft
{MODEL}
    - name: shared/editor
  workflow:
    start: writer
    edges:
      - from: writer
        to: [shared/editor]
    end: [shared/editor]
"""
        result = await self.call(body.encode(), workflow_service, formatter)
        assert result['valid'] is False
        assert result['errors'] == [
            {
                'path': 'arium.agents[1].name',
                'message': 'Agent not found: shared/editor',
            }
        ]

    async def test_stored_agent_is_accepted(self, workflow_service, formatter):
        body = f"""
arium:
  agents:
    - name: writer
      job: Write a draft
{MODEL}
    - name: shared/editor@3
  workflow:
    start: writer
    edges:
      - from: writer
        to: [shared/editor@3]
    end: [shared/editor@3]
"""
        result = await self.call(body.encode(), workflow_service, formatter)
        assert result['valid'] is True
        workflow_service.agent_crud_service.get_agent_yaml_from_bucket.assert_awaited_once_with(
            'editor', 'shared', version=3
        )

    async def test_missing_subworkflow_is_reported(self, workflow_service, formatter):
        body = f"""
arium:
  agents:
    - name: writer
      job: Write a draft
{MODEL}
  ariums:
    - name: shared/missing
  workflow:
    start: writer
    edges:
      - from: writer
        to: [missing]
    end: [missing]
"""
        result = await self.call(body.encode(), workflow_service, formatter)
        assert result['valid'] is False
        assert 'Workflow not found' in result['errors'][0]['message']

    async def test_subworkflow_is_inlined_before_validation(
        self, workflow_service, formatter
    ):
        workflow_service.get_workflow_yaml_from_bucket = AsyncMock(
            return_value=VALID_WORKFLOW_YAML
        )
        body = f"""
arium:
  agents:
    - name: starter
      job: Begin
{MODEL}
  ariums:
    - name: shared/pipeline
  workflow:
    start: starter
    edges:
      - from: starter
        to: [pipeline]
    end: [pipeline]
"""
        result = await self.call(body.encode(), workflow_service, formatter)
        assert result == {'valid': True, 'errors': []}

    async def test_unknown_function_node_is_reported(self, workflow_service, formatter):
        result = await self.call(
            FUNCTION_WORKFLOW_YAML.encode(), workflow_service, formatter
        )
        assert result['valid'] is False
        assert 'arium.function_nodes[0].function_name' in [
            e['path'] for e in result['errors']
        ]

    async def test_unknown_tool_on_an_inline_agent_is_reported(
        self, workflow_service, formatter
    ):
        body = VALID_WORKFLOW_YAML.replace(
            'job: Write a draft\n',
            'job: Write a draft\n      tools:\n        - name: ghost\n',
        )
        result = await self.call(body.encode(), workflow_service, formatter)
        assert result['valid'] is False
        assert 'arium.agents[0].tools[0].name' in [e['path'] for e in result['errors']]

    async def test_no_agent_is_built(self, workflow_service, formatter):
        with patch(
            'agents_module.services.workflow_crud_service.AriumBuilder'
        ) as builder:
            await self.call(VALID_WORKFLOW_YAML.encode(), workflow_service, formatter)
        builder.from_yaml.assert_not_called()


class TestWorkflowCreateUsesTheSameValidation:
    async def test_dangling_edge_is_rejected_before_any_build(self, workflow_service):
        body = VALID_WORKFLOW_YAML.replace('to: [editor]', 'to: [ghost]')
        with patch(
            'agents_module.services.workflow_crud_service.AriumBuilder'
        ) as builder:
            with pytest.raises(ValueError, match='Invalid workflow YAML configuration'):
                await workflow_service._validate_yaml_content(body, 'default', 'flow')
        builder.from_yaml.assert_not_called()
