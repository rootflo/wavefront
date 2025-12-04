from typing import Dict, List, Optional
from tools_module.registry.tool_loader import ToolLoader
from tools_module.interfaces.tool_details_provider import ToolDetailsProvider
from tools_module.models.tool_schemas import ToolExecutionDetails


class ToolService:
    """Service for managing tools and providing API endpoints"""

    def __init__(
        self, tool_loader: ToolLoader, tool_providers: List[ToolDetailsProvider]
    ):
        self.tool_loader = tool_loader
        self.tool_providers = tool_providers

    def get_available_tools(self) -> Dict:
        """
        Get all available tools with their metadata

        Returns:
            Dictionary containing all tool definitions with parameters and descriptions
        """
        return self.tool_loader.get_available_tools()

    def get_tool_names(self) -> List[str]:
        """
        Get list of available tool names

        Returns:
            List of tool names
        """
        return self.tool_loader.get_tool_names()

    def get_tool_metadata(self, tool_name: str) -> Optional[Dict]:
        """
        Get metadata for a specific tool

        Args:
            tool_name: Name of the tool

        Returns:
            Tool metadata dictionary or None if not found
        """
        return self.tool_loader.get_tool_metadata(tool_name)

    def get_tools_by_category(self, category: str) -> Dict:
        """
        Get tools filtered by category

        Args:
            category: Category to filter by (e.g., 'datasource')

        Returns:
            Dictionary of tools in the specified category
        """
        all_tools = self.get_available_tools()
        filtered_tools = {}

        for tool_name, tool_data in all_tools.items():
            if tool_data.get('category') == category:
                filtered_tools[tool_name] = tool_data

        return filtered_tools

    def validate_tool_exists(self, tool_name: str) -> bool:
        """
        Check if a tool exists

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool exists, False otherwise
        """
        return tool_name in self.get_tool_names()

    def validate_tools_exist(self, tool_names: List[str]) -> List[str]:
        """
        Validate multiple tool names and return any missing ones

        Args:
            tool_names: List of tool names to validate

        Returns:
            List of tool names that don't exist
        """
        available_tools = set(self.get_tool_names())
        missing_tools = []

        for tool_name in tool_names:
            if tool_name not in available_tools:
                missing_tools.append(tool_name)

        return missing_tools

    async def get_all_tool_details(self) -> List[ToolExecutionDetails]:
        """
        Get details for all available tools using registered providers

        Returns:
            List of tool details
        """
        tool_metadata = self.get_available_tools()
        all_tool_details = []

        for tool_name, tool_data in tool_metadata.items():
            category = tool_data.get('category', '')

            # Find the first provider that can handle this category
            # We prioritize specific providers over the default one
            # Assuming providers are ordered with specific ones first
            handled = False
            for provider in self.tool_providers:
                if provider.can_handle(category):
                    details = await provider.get_tool_details(tool_data)
                    all_tool_details.extend(details)
                    handled = True
                    break

            if not handled:
                # Should not happen if DefaultToolDetailsProvider is last
                pass

        return all_tool_details
