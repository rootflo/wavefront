from typing import List, Dict, Any
from tools_module.interfaces.tool_details_provider import ToolDetailsProvider
from tools_module.models.tool_schemas import ToolExecutionDetails
from tools_module.utils.api_service_tool_loader import (
    build_tool_parameters,
    extract_required_params,
    build_tool_description,
)
from api_services_module.core.manager import ApiServicesManager
from common_module.log.logger import logger
from api_services_module.config.parser import ServiceDefinitionParser


class ApiServiceToolDetailsProvider(ToolDetailsProvider):
    """Provider for expanding API service tools from database + YAML definitions"""

    def __init__(self, api_services_manager: ApiServicesManager):
        self.api_services_manager = api_services_manager

    def can_handle(self, category: str) -> bool:
        return category == 'api_service'

    async def get_tool_details(
        self, tool_metadata: Dict[str, Any]
    ) -> List[ToolExecutionDetails]:
        """
        Expand the trigger_api_service template into individual tools.

        For each API in each service:
        1. Fetch all API services from database
        2. Load YAML definitions from cloud storage
        3. Parse each API's payload_schema, path params, and query params
        4. Create a ToolExecutionDetails with API-specific parameters
        """
        tool_details = []

        # Fetch all API services from database
        all_services = await self.api_services_manager.get_all_api_services()

        if not all_services:
            logger.info('No API services found in database')
            return tool_details

        for service in all_services:
            try:
                # Skip inactive services
                if not service.is_active:
                    logger.debug(f'Skipping inactive service: {service.id}')
                    continue

                # Load YAML content from cloud storage
                yaml_content = self.api_services_manager.fetch_service_def(service)

                # Parse YAML to ServiceDefinition
                service_def = ServiceDefinitionParser.parse_yaml_string(yaml_content)

                # Create a tool for each API in the service
                for api_config in service_def.apis:
                    try:
                        tool_name = self._generate_tool_name(
                            service_def.id, api_config.id
                        )
                        parameters = build_tool_parameters(api_config)
                        required = extract_required_params(api_config)
                        description = build_tool_description(service_def, api_config)

                        tool_details.append(
                            ToolExecutionDetails(
                                name=tool_name,
                                resource_name=f'{service_def.id}/{api_config.id}',
                                prefill_parameter_names=[
                                    'api_service_id',
                                    'api_id',
                                    'api_version',
                                ],
                                prefilled_value={
                                    'api_service_id': service_def.id,
                                    'api_id': api_config.id,
                                    'api_version': api_config.version,
                                },
                                required=required,
                                parameters=parameters,
                                description=description,
                                category='api_service',
                            )
                        )
                        logger.debug(
                            f'Created tool: {tool_name} for service {service_def.id}'
                        )
                    except Exception as e:
                        logger.warning(
                            f'Error creating tool for API {api_config.id} in service {service_def.id}: {str(e)}, skipping'
                        )
                        continue

            except Exception as e:
                logger.warning(
                    f'Error loading service {service.id}: {str(e)}, skipping'
                )
                continue

        logger.info(f'Generated {len(tool_details)} API service tools')
        return tool_details

    def _generate_tool_name(self, service_id: str, api_id: str) -> str:
        """Generate tool name from service_id and api_id."""
        # Use _ separator between service and API
        # Example: "my-api-service" + "get-user" → "my-api-service_get-user"
        return f'{service_id}_{api_id}'
