from unittest.mock import AsyncMock
from flo_ai.tool.base_tool import Tool
from flo_ai.tool.tool_config import ToolConfig, create_tool_config


class TestToolConfig:
    """Test cases for ToolConfig functionality."""

    def test_tool_config_creation(self):
        """Test creating a tool configuration."""
        mock_function = AsyncMock(return_value='test_result')
        base_tool = Tool(
            name='test_tool',
            description='A test tool',
            function=mock_function,
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
            },
        )

        # Create tool config with pre-filled parameters
        tool_config = ToolConfig(
            tool=base_tool,
            pre_filled_params={'datasource_id': 'ds_123'},
            name_override='custom_name',
            description_override='Custom description',
        )

        assert tool_config.tool == base_tool
        assert tool_config.pre_filled_params == {'datasource_id': 'ds_123'}
        assert tool_config.name_override == 'custom_name'
        assert tool_config.description_override == 'Custom description'
        assert tool_config.is_partial() is True

    def test_tool_config_without_prefilled_params(self):
        """Test creating a tool configuration without pre-filled parameters."""
        mock_function = AsyncMock(return_value='test_result')
        base_tool = Tool(
            name='test_tool',
            description='A test tool',
            function=mock_function,
            parameters={
                'param1': {'type': 'string', 'description': 'Param 1', 'required': True}
            },
        )

        tool_config = ToolConfig(tool=base_tool)
        assert tool_config.tool == base_tool
        assert tool_config.pre_filled_params == {}
        assert tool_config.is_partial() is False

    def test_tool_config_to_tool_conversion(self):
        """Test converting tool configuration to tool."""
        mock_function = AsyncMock(return_value='test_result')
        base_tool = Tool(
            name='test_tool',
            description='A test tool',
            function=mock_function,
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
            },
        )

        # Test without pre-filled params (should return original tool)
        tool_config = ToolConfig(tool=base_tool)
        converted_tool = tool_config.to_tool()
        assert converted_tool == base_tool

        # Test with pre-filled params (should return partial tool)
        tool_config_with_params = ToolConfig(
            tool=base_tool, pre_filled_params={'datasource_id': 'ds_123'}
        )
        converted_tool = tool_config_with_params.to_tool()
        assert converted_tool.name == 'test_tool_partial'
        assert 'pre-configured parameters' in converted_tool.description

    def test_create_tool_config_helper_function(self):
        """Test the create_tool_config helper function."""
        mock_function = AsyncMock(return_value='test_result')
        base_tool = Tool(
            name='test_tool',
            description='A test tool',
            function=mock_function,
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
            },
        )

        tool_config = create_tool_config(
            base_tool, datasource_id='ds_123', project_id='my-project'
        )

        assert isinstance(tool_config, ToolConfig)
        assert tool_config.tool == base_tool
        assert tool_config.pre_filled_params == {
            'datasource_id': 'ds_123',
            'project_id': 'my-project',
        }
        assert tool_config.is_partial() is True
