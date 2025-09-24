from typing import Dict, Any, Optional
from .base_tool import Tool, ToolExecutionError
from flo_ai.utils.logger import logger


class PartialTool(Tool):
    """
    A tool that has some parameters pre-filled during agent building.
    The AI can still provide additional parameters during execution.
    """

    def __init__(
        self,
        base_tool: Tool,
        pre_filled_params: Dict[str, Any],
        name_override: Optional[str] = None,
        description_override: Optional[str] = None,
    ):
        """
        Create a partial tool with pre-filled parameters.

        Args:
            base_tool: The original tool to wrap
            pre_filled_params: Parameters to pre-fill (datasource_id, etc.)
            name_override: Optional custom name for the partial tool
            description_override: Optional custom description
        """
        self.base_tool = base_tool
        self.pre_filled_params = pre_filled_params.copy()

        # Create filtered parameters (remove pre-filled ones from AI's view)
        filtered_parameters = {}
        for param_name, param_info in base_tool.parameters.items():
            if param_name not in pre_filled_params:
                filtered_parameters[param_name] = param_info.copy()

        super().__init__(
            name=name_override or f'{base_tool.name}_partial',
            description=description_override
            or f'{base_tool.description} (with pre-configured parameters)',
            function=base_tool.function,
            parameters=filtered_parameters,
        )

    async def execute(self, **kwargs) -> Any:
        """Execute the tool with pre-filled parameters merged with AI-provided ones."""
        try:
            # Merge pre-filled params with AI-provided params
            # AI params take precedence over pre-filled ones
            merged_params = {**self.pre_filled_params, **kwargs}

            logger.info(
                f'Executing partial tool {self.name} with merged params: {merged_params}'
            )
            tool_result = await self.base_tool.function(**merged_params)
            logger.info(f'Partial tool {self.name} returned: {tool_result}')
            return tool_result
        except Exception as e:
            raise ToolExecutionError(
                f'Error executing partial tool {self.name}: {str(e)}', original_error=e
            )

    def get_original_tool(self) -> Tool:
        """Get the original tool without pre-filled parameters."""
        return self.base_tool

    def get_pre_filled_params(self) -> Dict[str, Any]:
        """Get the pre-filled parameters."""
        return self.pre_filled_params.copy()

    def add_pre_filled_param(self, key: str, value: Any) -> 'PartialTool':
        """Add or update a pre-filled parameter."""
        self.pre_filled_params[key] = value
        return self

    def remove_pre_filled_param(self, key: str) -> 'PartialTool':
        """Remove a pre-filled parameter."""
        if key in self.pre_filled_params:
            del self.pre_filled_params[key]
        return self


def create_partial_tool(tool: Tool, **pre_filled_params) -> PartialTool:
    """
    Create a partial tool with pre-filled parameters.

    Args:
        tool: The original tool
        **pre_filled_params: Parameters to pre-fill

    Returns:
        PartialTool: A tool with pre-filled parameters

    Example:
        # Original tool
        @flo_tool(description="Query BigQuery")
        async def bigquery_query(query: str, datasource_id: str, project_id: str):
            # implementation
            pass

        # Create partial tool with pre-filled datasource_id
        partial_tool = create_partial_tool(
            bigquery_query.tool,
            datasource_id="ds_123",
            project_id="my-project"
        )

        # AI only needs to provide the query
        result = await partial_tool.execute(query="SELECT * FROM users")
    """
    return PartialTool(tool, pre_filled_params)
