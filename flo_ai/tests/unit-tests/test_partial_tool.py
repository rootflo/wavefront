import pytest
from unittest.mock import AsyncMock
from flo_ai.tool.base_tool import Tool
from flo_ai.tool.partial_tool import PartialTool, create_partial_tool


class TestPartialTool:
    """Test cases for PartialTool functionality."""

    def test_partial_tool_creation(self):
        """Test creating a partial tool with pre-filled parameters."""
        # Create a mock base tool
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
                'project_id': {
                    'type': 'string',
                    'description': 'Project ID',
                    'required': True,
                },
            },
        )

        # Create partial tool with pre-filled datasource_id and project_id
        partial_tool = PartialTool(
            base_tool=base_tool,
            pre_filled_params={'datasource_id': 'ds_123', 'project_id': 'my-project'},
        )

        # Verify partial tool properties
        assert partial_tool.name == 'test_tool_partial'
        assert 'pre-configured parameters' in partial_tool.description
        assert partial_tool.base_tool == base_tool
        assert partial_tool.get_pre_filled_params() == {
            'datasource_id': 'ds_123',
            'project_id': 'my-project',
        }

        # Verify filtered parameters (only query should be visible to AI)
        assert 'query' in partial_tool.parameters
        assert 'datasource_id' not in partial_tool.parameters
        assert 'project_id' not in partial_tool.parameters
        assert partial_tool.parameters['query']['required'] is True

    def test_partial_tool_with_custom_name_and_description(self):
        """Test creating a partial tool with custom name and description."""
        mock_function = AsyncMock(return_value='test_result')
        base_tool = Tool(
            name='test_tool',
            description='A test tool',
            function=mock_function,
            parameters={
                'param1': {'type': 'string', 'description': 'Param 1', 'required': True}
            },
        )

        partial_tool = PartialTool(
            base_tool=base_tool,
            pre_filled_params={'param1': 'value1'},
            name_override='custom_name',
            description_override='Custom description',
        )

        assert partial_tool.name == 'custom_name'
        assert partial_tool.description == 'Custom description'

    @pytest.mark.asyncio
    async def test_partial_tool_execution(self):
        """Test executing a partial tool with merged parameters."""
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
                'project_id': {
                    'type': 'string',
                    'description': 'Project ID',
                    'required': True,
                },
            },
        )

        partial_tool = PartialTool(
            base_tool=base_tool,
            pre_filled_params={'datasource_id': 'ds_123', 'project_id': 'my-project'},
        )

        # Execute with AI-provided query
        result = await partial_tool.execute(query='SELECT * FROM users')

        # Verify the function was called with merged parameters
        mock_function.assert_called_once_with(
            query='SELECT * FROM users', datasource_id='ds_123', project_id='my-project'
        )
        assert result == 'test_result'

    @pytest.mark.asyncio
    async def test_partial_tool_execution_ai_params_override_prefilled(self):
        """Test that AI-provided parameters override pre-filled ones."""
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

        partial_tool = PartialTool(
            base_tool=base_tool, pre_filled_params={'datasource_id': 'ds_123'}
        )

        # Execute with AI-provided datasource_id that should override pre-filled one
        await partial_tool.execute(
            query='SELECT * FROM users',
            datasource_id='ds_456',  # This should override the pre-filled "ds_123"
        )

        # Verify the function was called with AI-provided datasource_id
        mock_function.assert_called_once_with(
            query='SELECT * FROM users',
            datasource_id='ds_456',  # AI-provided value should take precedence
        )

    def test_partial_tool_parameter_management(self):
        """Test adding and removing pre-filled parameters."""
        mock_function = AsyncMock(return_value='test_result')
        base_tool = Tool(
            name='test_tool',
            description='A test tool',
            function=mock_function,
            parameters={
                'param1': {'type': 'string', 'description': 'Param 1', 'required': True}
            },
        )

        partial_tool = PartialTool(
            base_tool=base_tool, pre_filled_params={'param1': 'value1'}
        )

        # Test adding a parameter
        partial_tool.add_pre_filled_param('param2', 'value2')
        assert partial_tool.get_pre_filled_params() == {
            'param1': 'value1',
            'param2': 'value2',
        }

        # Test removing a parameter
        partial_tool.remove_pre_filled_param('param1')
        assert partial_tool.get_pre_filled_params() == {'param2': 'value2'}

        # Test removing non-existent parameter (should not raise error)
        partial_tool.remove_pre_filled_param('non_existent')
        assert partial_tool.get_pre_filled_params() == {'param2': 'value2'}

    def test_create_partial_tool_helper_function(self):
        """Test the create_partial_tool helper function."""
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

        # Use helper function
        partial_tool = create_partial_tool(
            base_tool, datasource_id='ds_123', project_id='my-project'
        )

        assert isinstance(partial_tool, PartialTool)
        assert partial_tool.get_pre_filled_params() == {
            'datasource_id': 'ds_123',
            'project_id': 'my-project',
        }

    @pytest.mark.asyncio
    async def test_partial_tool_error_handling(self):
        """Test error handling in partial tool execution."""
        # Create a mock function that raises an exception
        mock_function = AsyncMock(side_effect=Exception('Test error'))
        base_tool = Tool(
            name='test_tool',
            description='A test tool',
            function=mock_function,
            parameters={
                'param1': {'type': 'string', 'description': 'Param 1', 'required': True}
            },
        )

        partial_tool = PartialTool(
            base_tool=base_tool, pre_filled_params={'param1': 'value1'}
        )

        # Execute and expect ToolExecutionError
        with pytest.raises(Exception) as exc_info:
            await partial_tool.execute()

        assert 'Error executing partial tool' in str(exc_info.value)
        assert 'Test error' in str(exc_info.value)

    def test_partial_tool_parameter_filtering(self):
        """Test that pre-filled parameters are properly filtered from AI view."""
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
                'project_id': {
                    'type': 'string',
                    'description': 'Project ID',
                    'required': True,
                },
                'optional_param': {
                    'type': 'string',
                    'description': 'Optional param',
                    'required': False,
                },
            },
        )

        # Pre-fill some required and some optional parameters
        partial_tool = PartialTool(
            base_tool=base_tool,
            pre_filled_params={
                'datasource_id': 'ds_123',
                'project_id': 'my-project',
                'optional_param': 'default_value',
            },
        )

        # Only non-pre-filled parameters should be visible to AI
        ai_visible_params = partial_tool.parameters
        assert 'query' in ai_visible_params
        assert 'datasource_id' not in ai_visible_params
        assert 'project_id' not in ai_visible_params
        assert 'optional_param' not in ai_visible_params

        # Verify the parameter info is preserved
        assert ai_visible_params['query']['type'] == 'string'
        assert ai_visible_params['query']['required'] is True
