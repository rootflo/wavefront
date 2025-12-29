from typing import List, Dict, Any
import re
from tools_module.interfaces.tool_details_provider import ToolDetailsProvider
from tools_module.models.tool_schemas import ToolExecutionDetails
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
                        parameters = self._build_parameters(api_config)
                        required = self._extract_required_params(api_config)
                        description = self._build_description(service_def, api_config)

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

    def _build_parameters(self, api_config) -> Dict[str, Any]:
        """
        Build tool parameters from API configuration.

        Parameters include:
        1. Payload schema fields (from payload_schema)
        2. Path parameters (extracted from path template)
        3. Query parameters (from backend_query_params)
        """
        parameters = {}

        # Add prefilled parameters (not shown to user but needed for execution)
        parameters['api_service_id'] = {
            'type': 'string',
            'description': 'ID of the API service (automatically filled)',
        }
        parameters['api_id'] = {
            'type': 'string',
            'description': 'ID of the API endpoint (automatically filled)',
        }
        parameters['api_version'] = {
            'type': 'string',
            'description': 'API version (automatically filled)',
        }

        # Extract path parameters from path template
        path_params = self._extract_path_params(api_config.path)
        for param_name in path_params:
            parameters[f'path_{param_name}'] = {
                'type': 'string',
                'description': f'Path parameter: {param_name}',
            }

        # Add query parameters from backend_query_params
        for param_name, default_value in api_config.backend_query_params.items():
            param_type = self._infer_type(default_value)
            parameters[f'query_{param_name}'] = {
                'type': param_type,
                'description': f'Query parameter: {param_name}',
            }

        # Add payload schema fields
        if api_config.payload_schema:
            for field in api_config.payload_schema.fields:
                parameters[field.name] = {
                    'type': field.type,
                    'description': field.description or f'Payload field: {field.name}',
                }

        return parameters

    def _extract_required_params(self, api_config) -> List[str]:
        """Extract required parameter names."""
        required = []

        # Path parameters are always required
        path_params = self._extract_path_params(api_config.path)
        required.extend([f'path_{param}' for param in path_params])

        # Required payload fields
        if api_config.payload_schema:
            for field in api_config.payload_schema.fields:
                if field.required:
                    required.append(field.name)

        return required

    def _extract_path_params(self, path: str) -> List[str]:
        """
        Extract parameter names from path template.

        Example: "/users/{user_id}/posts/{post_id}" → ["user_id", "post_id"]
        """
        # Use regex to find all {param_name} patterns
        pattern = r'\{([^}]+)\}'
        matches = re.findall(pattern, path)
        return matches

    def _infer_type(self, value: Any) -> str:
        """Infer JSON schema type from Python value."""
        if isinstance(value, bool):
            return 'boolean'
        elif isinstance(value, int):
            return 'integer'
        elif isinstance(value, float):
            return 'number'
        elif isinstance(value, list):
            return 'array'
        elif isinstance(value, dict):
            return 'object'
        else:
            return 'string'

    def _build_description(self, service_def, api_config) -> str:
        """Build tool description from service and API metadata."""
        # Use the API's description if available, otherwise build a default description
        if api_config.description:
            return api_config.description

        # Fallback to default description
        desc_parts = [
            f'Execute {service_def.id} API: {api_config.id}.',
            f'Method: {api_config.method.value}.',
        ]

        # Add API-specific description if available from payload schema
        if api_config.payload_schema and api_config.payload_schema.fields:
            desc_parts.append(
                f'Accepts {len(api_config.payload_schema.fields)} parameter(s).'
            )

        return ' '.join(desc_parts)
