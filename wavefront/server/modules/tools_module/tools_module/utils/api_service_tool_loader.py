"""Utility for dynamically loading API service tools."""

import re
from typing import Optional, Dict, Any, List
from flo_ai.tool.base_tool import Tool
from api_services_module.core.manager import ApiServicesManager
from api_services_module.config.parser import ServiceDefinitionParser
from common_module.log.logger import logger
from tools_module.utils.api_service_fn import execute_api_service_fn


def extract_path_params(path: str) -> List[str]:
    """
    Extract parameter names from path template.

    Example: "/users/{user_id}/posts/{post_id}" → ["user_id", "post_id"]
    """
    pattern = r'\{([^}]+)\}'
    matches = re.findall(pattern, path)
    return matches


def infer_type(value: Any) -> str:
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


def build_tool_parameters(api_config) -> Dict[str, Any]:
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
    path_params = extract_path_params(api_config.path)
    for param_name in path_params:
        parameters[f'path_{param_name}'] = {
            'type': 'string',
            'description': f'Path parameter: {param_name}',
        }

    # Add query parameters from backend_query_params
    for param_name, default_value in api_config.backend_query_params.items():
        param_type = infer_type(default_value)
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


def extract_required_params(api_config) -> List[str]:
    """Extract required parameter names from API configuration."""
    required = []

    # Path parameters are always required
    path_params = extract_path_params(api_config.path)
    required.extend([f'path_{param}' for param in path_params])

    # Required payload fields
    if api_config.payload_schema:
        for field in api_config.payload_schema.fields:
            if field.required:
                required.append(field.name)

    return required


def build_tool_description(service_def, api_config) -> str:
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


async def load_api_service_tool(
    tool_name: str, api_services_manager: Optional[ApiServicesManager]
) -> Optional[Tool]:
    """
    Attempt to load an API service as a Tool object.

    Args:
        tool_name: Name of the tool in format "service_id_api_id"
        api_services_manager: API services manager instance

    Returns:
        Tool object if API service found, None otherwise
    """
    try:
        # Check if api_services_manager is available
        if not api_services_manager:
            return None

        # Parse tool name to extract service_id and api_id
        if '_' not in tool_name:
            return None

        parts = tool_name.split('_', 1)
        service_id = parts[0]
        api_id = parts[1]

        # Query API service by id
        service = await api_services_manager.get_api_service(id=service_id)

        if not service or not service.is_active:
            return None

        # Load YAML content
        yaml_content = api_services_manager.fetch_service_def(service)

        # Parse YAML to ServiceDefinition
        service_def = ServiceDefinitionParser.parse_yaml_string(yaml_content)

        # Find the specific API config
        api_config = service_def.get_api_by_id(api_id)
        if not api_config:
            return None

        # Build parameters, description using shared helpers
        parameters = build_tool_parameters(api_config)
        description = build_tool_description(service_def, api_config)

        # Create Tool object
        tool = Tool(
            name=tool_name,
            description=description,
            function=execute_api_service_fn,
            parameters=parameters,
        )

        logger.info(f'Dynamically loaded API service tool: {tool_name}')
        return tool

    except Exception as e:
        logger.debug(f'API service {tool_name} not found: {str(e)}')
        return None
