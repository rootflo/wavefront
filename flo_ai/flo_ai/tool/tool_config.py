from typing import Dict, Any, Optional
from .base_tool import Tool


class ToolConfig:
    """
    Represents a tool with optional pre-filled parameters.
    This allows the AgentBuilder to handle both regular tools and tools with configurations
    transparently through the same interface.
    """

    def __init__(
        self,
        tool: Tool,
        pre_filled_params: Optional[Dict[str, Any]] = None,
        name_override: Optional[str] = None,
        description_override: Optional[str] = None,
    ):
        """
        Create a tool configuration.

        Args:
            tool: The base tool
            pre_filled_params: Optional pre-filled parameters
            name_override: Optional custom name
            description_override: Optional custom description
        """
        self.tool = tool
        self.pre_filled_params = pre_filled_params or {}
        self.name_override = name_override
        self.description_override = description_override

    def is_partial(self) -> bool:
        """Check if this tool configuration has pre-filled parameters."""
        return bool(self.pre_filled_params)

    def to_tool(self) -> Tool:
        """Convert this configuration to a Tool (either original or partial)."""
        # If there are pre-filled parameters or custom name/description, create partial tool
        if (
            self.pre_filled_params
            or self.name_override is not None
            or self.description_override is not None
        ):
            # Import here to avoid circular imports
            from .partial_tool import PartialTool

            return PartialTool(
                base_tool=self.tool,
                pre_filled_params=self.pre_filled_params,
                name_override=self.name_override,
                description_override=self.description_override,
            )
        else:
            # No customizations, return original tool
            return self.tool


def create_tool_config(tool: Tool, **pre_filled_params) -> ToolConfig:
    """
    Create a tool configuration with pre-filled parameters.

    Args:
        tool: The base tool
        **pre_filled_params: Pre-filled parameters

    Returns:
        ToolConfig: A tool configuration
    """
    return ToolConfig(tool, pre_filled_params)
