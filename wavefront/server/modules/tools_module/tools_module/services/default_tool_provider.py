from typing import List, Dict, Any
from tools_module.interfaces.tool_details_provider import ToolDetailsProvider
from tools_module.models.tool_schemas import ToolExecutionDetails


class DefaultToolDetailsProvider(ToolDetailsProvider):
    def can_handle(self, category: str) -> bool:
        return True  # Fallback for everything else

    async def get_tool_details(
        self, tool_metadata: Dict[str, Any]
    ) -> List[ToolExecutionDetails]:
        return [
            ToolExecutionDetails(
                name=tool_metadata['name'],
                resource_name='',
                prefill_parameter_names=tool_metadata.get('prefill_values', []),
                prefilled_value={},
                required=tool_metadata.get('required', []),
                parameters=tool_metadata['parameters'],
                description=tool_metadata['description'],
                category=tool_metadata.get('category', ''),
            )
        ]
