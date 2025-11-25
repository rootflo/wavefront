import pytest
from unittest.mock import Mock, AsyncMock
from flo_ai.tool.base_tool import Tool
from flo_ai.tool.tool_config import ToolConfig
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.llm import OpenAI


class TestAgentBuilderTools:
    """Test cases for AgentBuilder tool functionality."""

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

    def test_with_tools_regular_tools(self):
        """Test adding regular tools to agent builder."""
        builder = AgentBuilder()
        builder.with_tools([self.base_tool])

        assert len(builder._tools) == 1
        assert builder._tools[0] == self.base_tool

    def test_with_tools_tool_configs(self):
        """Test adding tool configurations to agent builder."""
        tool_config = ToolConfig(
            tool=self.base_tool,
            prefilled_params={'datasource_id': 'ds_123', 'project_id': 'my-project'},
        )

        builder = AgentBuilder()
        builder.with_tools([tool_config])

        assert len(builder._tools) == 1
        # Should be converted to a partial tool
        assert builder._tools[0].name == 'test_tool_partial'
        assert 'pre-configured parameters' in builder._tools[0].description

    def test_with_tools_tool_dictionaries(self):
        """Test adding tool dictionaries to agent builder."""
        tool_dict = {
            'tool': self.base_tool,
            'prefilled_params': {
                'datasource_id': 'ds_123',
                'project_id': 'my-project',
            },
            'name_override': 'custom_tool_name',
            'description_override': 'Custom tool description',
        }

        builder = AgentBuilder()
        builder.with_tools([tool_dict])

        assert len(builder._tools) == 1
        # Should be converted to a partial tool with custom name and description
        assert builder._tools[0].name == 'custom_tool_name'
        assert builder._tools[0].description == 'Custom tool description'

    def test_with_tools_mixed_types(self):
        """Test adding mixed tool types to agent builder."""
        tool_config = ToolConfig(
            tool=self.base_tool, prefilled_params={'datasource_id': 'ds_123'}
        )

        tool_dict = {
            'tool': self.base_tool,
            'prefilled_params': {'project_id': 'my-project'},
        }

        builder = AgentBuilder()
        builder.with_tools([self.base_tool, tool_config, tool_dict])

        assert len(builder._tools) == 3
        # First tool should be the original
        assert builder._tools[0] == self.base_tool
        # Second and third should be partial tools
        assert 'partial' in builder._tools[1].name
        assert 'partial' in builder._tools[2].name

    def test_with_tools_invalid_type(self):
        """Test that invalid tool types raise an error."""
        builder = AgentBuilder()

        with pytest.raises(ValueError, match='Unsupported tool type'):
            builder.with_tools(['invalid_tool'])

    def test_add_tool_regular_tool(self):
        """Test adding a regular tool using add_tool method."""
        builder = AgentBuilder()
        builder.add_tool(self.base_tool)

        assert len(builder._tools) == 1
        assert builder._tools[0] == self.base_tool

    def test_add_tool_with_prefilled_params(self):
        """Test adding a tool with pre-filled parameters using add_tool method."""
        builder = AgentBuilder()
        builder.add_tool(
            self.base_tool, datasource_id='ds_123', project_id='my-project'
        )

        assert len(builder._tools) == 1
        # Should be converted to a partial tool
        assert builder._tools[0].name == 'test_tool_partial'
        assert 'pre-configured parameters' in builder._tools[0].description

    def test_add_tool_multiple_tools(self):
        """Test adding multiple tools using add_tool method."""
        builder = AgentBuilder()
        builder.add_tool(self.base_tool)  # Regular tool
        builder.add_tool(
            self.base_tool, datasource_id='ds_123'
        )  # Tool with pre-filled params

        assert len(builder._tools) == 2
        assert builder._tools[0] == self.base_tool  # Original tool
        assert 'partial' in builder._tools[1].name  # Partial tool

    def test_build_agent_with_tools(self):
        """Test building an agent with tools."""
        # Mock LLM
        mock_llm = Mock(spec=OpenAI)

        builder = AgentBuilder()
        agent = (
            builder.with_name('Test Agent')
            .with_prompt('You are a test agent')
            .with_llm(mock_llm)
            .add_tool(self.base_tool)
            .add_tool(self.base_tool, datasource_id='ds_123', project_id='my-project')
            .build()
        )

        assert agent.name == 'Test Agent'
        assert agent.system_prompt == 'You are a test agent'
        assert agent.llm == mock_llm
        assert len(agent.tools) == 2
        assert agent.tools[0] == self.base_tool
        assert 'partial' in agent.tools[1].name

    def test_tool_parameter_filtering(self):
        """Test that pre-filled parameters are properly filtered from AI view."""
        builder = AgentBuilder()
        builder.add_tool(
            self.base_tool, datasource_id='ds_123', project_id='my-project'
        )

        # The tool should have only non-pre-filled parameters visible to AI
        partial_tool = builder._tools[0]
        ai_visible_params = partial_tool.parameters

        assert 'query' in ai_visible_params
        assert 'datasource_id' not in ai_visible_params
        assert 'project_id' not in ai_visible_params

    def test_tool_execution_with_merged_params(self):
        """Test that tool execution merges pre-filled and AI-provided parameters."""
        builder = AgentBuilder()
        builder.add_tool(
            self.base_tool, datasource_id='ds_123', project_id='my-project'
        )

        partial_tool = builder._tools[0]

        # Execute with AI-provided query
        import asyncio

        result = asyncio.run(partial_tool.execute(query='SELECT * FROM users'))

        # Verify the function was called with merged parameters
        self.mock_function.assert_called_once_with(
            query='SELECT * FROM users', datasource_id='ds_123', project_id='my-project'
        )
        assert result == 'test_result'
