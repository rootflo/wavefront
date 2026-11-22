from typing import List, Dict, Any
from datasource.types import is_file_storage_type
from tools_module.interfaces.tool_details_provider import ToolDetailsProvider
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.models.datasource import Datasource
from tools_module.models.tool_schemas import ToolExecutionDetails


class DatasourceToolDetailsProvider(ToolDetailsProvider):
    def __init__(self, datasource_repository: SQLAlchemyRepository[Datasource]):
        self.datasource_repository = datasource_repository

    def can_handle(self, category: str) -> bool:
        return category == 'datasource'

    async def get_tool_details(
        self, tool_metadata: Dict[str, Any]
    ) -> List[ToolExecutionDetails]:
        tool_details = []
        prefill_values = tool_metadata.get('prefill_values', [])

        if 'datasource_id' in prefill_values:
            all_datasource = await self.datasource_repository.find()
            # File tools only work on file storage datasources and SQL tools
            # only on SQL ones, so each tool is offered for its own kind.
            wants_file_storage = tool_metadata.get('datasource_kind') == 'file_storage'
            all_datasource = [
                datasource.to_dict()
                for datasource in all_datasource
                if is_file_storage_type(datasource.type) == wants_file_storage
            ]

            for datasource in all_datasource:
                tool_details.append(
                    ToolExecutionDetails(
                        name=tool_metadata['name'],
                        prefill_parameter_names=prefill_values,
                        prefilled_value={
                            'datasource_id': datasource['id'],
                        },
                        resource_name=datasource['name'],
                        required=tool_metadata.get('required', []),
                        parameters=tool_metadata['parameters'],
                        description=tool_metadata['description'],
                        category=tool_metadata['category'],
                    )
                )
        else:
            # Fallback if no datasource_id prefill is expected, though unlikely for this category based on current logic
            tool_details.append(
                ToolExecutionDetails(
                    name=tool_metadata['name'],
                    resource_name='',
                    prefill_parameter_names=prefill_values,
                    prefilled_value={},
                    required=tool_metadata.get('required', []),
                    parameters=tool_metadata['parameters'],
                    description=tool_metadata['description'],
                    category=tool_metadata['category'],
                )
            )

        return tool_details
