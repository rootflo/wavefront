from abc import ABC, abstractmethod
from typing import List, Dict, Any
from tools_module.models.tool_schemas import ToolExecutionDetails


class ToolDetailsProvider(ABC):
    """Interface for providing tool details"""

    @abstractmethod
    async def get_tool_details(
        self, tool_metadata: Dict[str, Any]
    ) -> List[ToolExecutionDetails]:
        """
        Get details for a specific tool based on its metadata.

        Args:
            tool_metadata: The metadata of the tool from available_tools.json

        Returns:
            List of tool details (can be multiple if expanded like datasources)
        """
        pass

    @abstractmethod
    def can_handle(self, category: str) -> bool:
        """
        Check if this provider can handle the given tool category.

        Args:
            category: The category of the tool

        Returns:
            True if this provider handles the category, False otherwise
        """
        pass
