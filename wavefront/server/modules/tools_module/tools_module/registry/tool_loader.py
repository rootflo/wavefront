import json
import os
from typing import Callable, Dict, List, Mapping, Optional
from flo_ai.tool.base_tool import Tool
from tools_module.registry.function_node_registry import build_function_node_registry


class ToolLoader:
    """Handles loading and management of tools from the registry"""

    def __init__(
        self,
        function_registry: Mapping[str, Callable],
        tools_json_path: Optional[str] = None,
    ):
        """
        Initialize tool loader

        Args:
            function_registry: Tool functions by name, already bound to the
                services they call (see ``build_function_registry``)
            tools_json_path: Path to available_tools.json file
        """
        if tools_json_path is None:
            # Default to available_tools.json in the module root
            current_dir = os.path.dirname(os.path.dirname(__file__))
            tools_json_path = os.path.join(current_dir, 'available_tools.json')

        self.tools_json_path = tools_json_path
        self.function_registry = function_registry
        self._tools_metadata = None
        self._function_node_registry: Optional[Dict[str, Callable]] = None

    @property
    def function_node_registry(self) -> Dict[str, Callable]:
        """Function-node adapters for every registry function (built once)."""
        if self._function_node_registry is None:
            self._function_node_registry = build_function_node_registry(
                self.function_registry
            )
        return self._function_node_registry

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
        tool_function = self.function_registry.get(tool_name)
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
