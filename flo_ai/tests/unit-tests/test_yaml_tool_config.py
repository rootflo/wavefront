import pytest
from unittest.mock import Mock, AsyncMock
from flo_ai.tool.base_tool import Tool
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.llm import OpenAI


class TestYamlToolConfig:
    """Test cases for YAML tool configuration functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_function = AsyncMock(return_value='test_result')
        self.base_tool = Tool(
            name='test_tool',
            description='A test tool',
            function=self.mock_function,
            parameters={
                'query': {
                    'type': 'string',
                    'description': 'Query string',
                    'required': True,
                },
                'datasource_id': {
                    'type': 'string',
                    'description': 'Data source ID',
                    'required': True,
                },
                'project_id': {
                    'type': 'string',
                    'description': 'Project ID',
                    'required': True,
                },
            },
        )

        self.tool_registry = {
            'test_tool': self.base_tool,
            'another_tool': self.base_tool,
        }

    def test_simple_tool_reference(self):
        """Test YAML with simple tool references."""
        yaml_str = """
agent:
  name: "Test Agent"
  job: "You are a test agent"
  model:
    provider: "openai"
    name: "gpt-4"
  tools:
    - "test_tool"
    - "another_tool"
"""

        # Mock LLM to avoid API key requirement
        mock_llm = Mock(spec=OpenAI)

        agent = AgentBuilder.from_yaml(
            yaml_str, tool_registry=self.tool_registry, base_llm=mock_llm
        )

        assert agent._name == 'Test Agent'
        assert agent._system_prompt == 'You are a test agent'
        assert len(agent._tools) == 2
        assert agent._tools[0] == self.base_tool
        assert agent._tools[1] == self.base_tool

    def test_tool_configuration_with_prefilled_params(self):
        """Test YAML with tool configuration and pre-filled parameters."""
        yaml_str = """
agent:
  name: "Test Agent"
  job: "You are a test agent"
  model:
    provider: "openai"
    name: "gpt-4"
  tools:
    - name: "test_tool"
      pre_filled_params:
        datasource_id: "ds_123"
        project_id: "my-project"
      name_override: "custom_tool_name"
      description_override: "Custom tool description"
"""

        # Mock LLM to avoid API key requirement
        mock_llm = Mock(spec=OpenAI)

        agent = AgentBuilder.from_yaml(
            yaml_str, tool_registry=self.tool_registry, base_llm=mock_llm
        )

        assert agent._name == 'Test Agent'
        assert len(agent._tools) == 1

        # Check that the tool is a partial tool with custom name and description
        tool = agent._tools[0]
        assert tool.name == 'custom_tool_name'
        assert tool.description == 'Custom tool description'

        # Check that pre-filled parameters are hidden from AI
        ai_visible_params = tool.parameters
        assert 'query' in ai_visible_params
        assert 'datasource_id' not in ai_visible_params
        assert 'project_id' not in ai_visible_params

    def test_mixed_tool_types(self):
        """Test YAML with mixed tool types (simple references and configurations)."""
        yaml_str = """
agent:
  name: "Test Agent"
  job: "You are a test agent"
  model:
    provider: "openai"
    name: "gpt-4"
  tools:
    - "test_tool"  # Simple reference
    - name: "another_tool"
      pre_filled_params:
        datasource_id: "ds_456"
        project_id: "another-project"
"""

        # Mock LLM to avoid API key requirement
        mock_llm = Mock(spec=OpenAI)

        agent = AgentBuilder.from_yaml(
            yaml_str, tool_registry=self.tool_registry, base_llm=mock_llm
        )

        assert len(agent._tools) == 2

        # First tool should be the original tool
        assert agent._tools[0] == self.base_tool

        # Second tool should be a partial tool
        assert 'partial' in agent._tools[1].name

    def test_tool_not_found_in_registry(self):
        """Test error when tool is not found in registry."""
        yaml_str = """
agent:
  name: "Test Agent"
  job: "You are a test agent"
  model:
    provider: "openai"
    name: "gpt-4"
  tools:
    - "nonexistent_tool"
"""

        # Mock LLM to avoid API key requirement
        mock_llm = Mock(spec=OpenAI)

        with pytest.raises(
            ValueError, match="Tool 'nonexistent_tool' not found in tool registry"
        ):
            AgentBuilder.from_yaml(
                yaml_str, tool_registry=self.tool_registry, base_llm=mock_llm
            )

    def test_tool_configuration_missing_name(self):
        """Test error when tool configuration is missing name field."""
        yaml_str = """
agent:
  name: "Test Agent"
  job: "You are a test agent"
  model:
    provider: "openai"
    name: "gpt-4"
  tools:
    - pre_filled_params:
        datasource_id: "ds_123"
"""

        # Mock LLM to avoid API key requirement
        mock_llm = Mock(spec=OpenAI)

        with pytest.raises(
            ValueError, match="Tool configuration must have a 'name' field"
        ):
            AgentBuilder.from_yaml(
                yaml_str, tool_registry=self.tool_registry, base_llm=mock_llm
            )

    def test_invalid_tool_configuration_type(self):
        """Test error when tool configuration has invalid type."""
        yaml_str = """
agent:
  name: "Test Agent"
  job: "You are a test agent"
  model:
    provider: "openai"
    name: "gpt-4"
  tools:
    - 123  # Invalid type
"""

        # Mock LLM to avoid API key requirement
        mock_llm = Mock(spec=OpenAI)

        with pytest.raises(ValueError, match='Invalid tool configuration type'):
            AgentBuilder.from_yaml(
                yaml_str, tool_registry=self.tool_registry, base_llm=mock_llm
            )

    def test_no_tool_registry_provided(self):
        """Test error when no tool registry is provided but tools are referenced."""
        yaml_str = """
agent:
  name: "Test Agent"
  job: "You are a test agent"
  model:
    provider: "openai"
    name: "gpt-4"
  tools:
    - "test_tool"
"""

        # Mock LLM to avoid API key requirement
        mock_llm = Mock(spec=OpenAI)

        with pytest.raises(
            ValueError, match="Tool 'test_tool' not found in tool registry"
        ):
            AgentBuilder.from_yaml(yaml_str, tool_registry=None, base_llm=mock_llm)

    def test_tool_configuration_without_prefilled_params(self):
        """Test tool configuration without pre-filled parameters."""
        yaml_str = """
agent:
  name: "Test Agent"
  job: "You are a test agent"
  model:
    provider: "openai"
    name: "gpt-4"
  tools:
    - name: "test_tool"
      name_override: "custom_tool_name"
      description_override: "Custom tool description"
"""

        # Mock LLM to avoid API key requirement
        mock_llm = Mock(spec=OpenAI)

        agent = AgentBuilder.from_yaml(
            yaml_str, tool_registry=self.tool_registry, base_llm=mock_llm
        )

        assert len(agent._tools) == 1
        tool = agent._tools[0]

        # Should be a partial tool with custom name and description
        assert tool.name == 'custom_tool_name'
        assert tool.description == 'Custom tool description'
        # Should be a partial tool because we have name_override and description_override
        assert hasattr(tool, 'base_tool')  # Partial tool has base_tool attribute

    def test_process_yaml_tools_method(self):
        """Test the _process_yaml_tools method directly."""
        tools_config = [
            'test_tool',  # Simple reference
            {
                'name': 'another_tool',
                'pre_filled_params': {'datasource_id': 'ds_123'},
                'name_override': 'custom_name',
            },
        ]

        processed_tools = AgentBuilder._process_yaml_tools(
            tools_config, self.tool_registry
        )

        assert len(processed_tools) == 2
        assert processed_tools[0] == self.base_tool  # Simple reference
        assert (
            processed_tools[1].name == 'custom_name'
        )  # Configuration with name_override
        assert hasattr(processed_tools[1], 'base_tool')  # Should be a partial tool
