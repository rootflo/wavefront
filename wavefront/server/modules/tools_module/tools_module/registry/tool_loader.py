import json
import os
from typing import Dict, List, Optional
from flo_ai.tool.base_tool import Tool
from tools_module.registry.function_registry import FUNCTION_REGISTRY


class ToolLoader:
    """Handles loading and management of tools from the registry"""

    def __init__(
        self,
        tools_json_path: Optional[str] = None,
    ):
        """
        Initialize tool loader

        Args:
            tools_json_path: Path to available_tools.json file
        """
        if tools_json_path is None:
            # Default to available_tools.json in the module root
            current_dir = os.path.dirname(os.path.dirname(__file__))
            tools_json_path = os.path.join(current_dir, 'available_tools.json')

        self.tools_json_path = tools_json_path
        self._tools_metadata = None

    def _load_tools_metadata(self) -> Dict:
        """Load tools metadata from JSON file"""
        if self._tools_metadata is None:
            with open(self.tools_json_path, 'r') as f:
                self._tools_metadata = json.load(f)
        return self._tools_metadata

    def get_available_tools(self) -> Dict:
        """Get all available tools metadata"""
        return self._load_tools_metadata()

    def get_tool_names(self) -> List[str]:
        """Get list of available tool names"""
        return list(self._load_tools_metadata().keys())

    def get_tool_metadata(self, tool_name: str) -> Optional[Dict]:
        """Get metadata for a specific tool"""
        tools_metadata = self._load_tools_metadata()
        return tools_metadata.get(tool_name)

    def load_tool(self, tool_name: str) -> Optional[Tool]:
        """
        Load a specific tool by name

        Args:
            tool_name: Name of the tool to load

        Returns:
            flo_ai.Tool instance or None if tool not found
        """
        # Get tool metadata
        tool_metadata = self.get_tool_metadata(tool_name)
        if not tool_metadata:
            return None

        # Get tool function from registry
        tool_function = FUNCTION_REGISTRY.get(tool_name)
        if not tool_function:
            return None

        # Create Tool instance
        return Tool(
            name=tool_metadata['name'],
            description=tool_metadata['description'],
            function=tool_function,
            parameters=tool_metadata['parameters'],
        )

    def load_tools(self, tool_names: List[str]) -> List[Tool]:
        """
        Load multiple tools by names

        Args:
            tool_names: List of tool names to load

        Returns:
            List of flo_ai.Tool instances
        """
        tools = []
        for tool_name in tool_names:
            tool = self.load_tool(tool_name)
            if tool:
                tools.append(tool)
        return tools

    def load_all_tools(self) -> List[Tool]:
        """Load all available tools"""
        return self.load_tools(self.get_tool_names())

    def load_tool_with_name(self, tool_name: str) -> Optional[Tool]:
        """Load a tool by name"""
        return self.load_tool(tool_name)
