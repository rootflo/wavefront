from typing import Any, Dict, List

from db_repo_module.models.email_connection import EmailConnection
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from tools_module.interfaces.tool_details_provider import ToolDetailsProvider
from tools_module.models.tool_schemas import ToolExecutionDetails


class EmailToolDetailsProvider(ToolDetailsProvider):
    """Expands the email tool into one selectable tool per connected mailbox.

    The connection id is prefilled rather than exposed as a parameter, so an
    agent can only send from the mailbox it was configured with.
    """

    def __init__(
        self, email_connection_repository: SQLAlchemyRepository[EmailConnection]
    ):
        self.email_connection_repository = email_connection_repository

    def can_handle(self, category: str) -> bool:
        return category == 'email'

    async def get_tool_details(
        self, tool_metadata: Dict[str, Any]
    ) -> List[ToolExecutionDetails]:
        prefill_values = tool_metadata.get('prefill_values', [])

        if 'connection_id' not in prefill_values:
            return [
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
            ]

        connections = await self.email_connection_repository.find(status='active')
        return [
            ToolExecutionDetails(
                name=tool_metadata['name'],
                prefill_parameter_names=prefill_values,
                prefilled_value={'connection_id': str(connection.id)},
                resource_name=f'{connection.name} ({connection.mailbox_email})',
                required=tool_metadata.get('required', []),
                parameters=tool_metadata['parameters'],
                description=tool_metadata['description'],
                category=tool_metadata['category'],
            )
            for connection in connections
        ]
