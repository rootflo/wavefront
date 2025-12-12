"""YAML service definition parser."""

import yaml
from typing import Dict, Any, List
from ..models.service import (
    ServiceDefinition,
    AuthConfig,
    ApiConfig,
    AuthType,
    HttpMethod,
)


class ServiceDefinitionParser:
    """Parser for YAML service definition files."""

    @staticmethod
    def parse_yaml_string(yaml_content: str) -> ServiceDefinition:
        """
        Parse a YAML service definition from string.

        Args:
            yaml_content: YAML content as string

        Returns:
            ServiceDefinition object
        """
        try:
            yaml_data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise TypeError(f'Invalid YAML content: {str(e)}')

        return ServiceDefinitionParser._parse_service_data(yaml_data)

    @staticmethod
    def _parse_service_data(yaml_data: Dict[str, Any]) -> ServiceDefinition:
        """Parse service data from loaded YAML."""
        if 'service' not in yaml_data:
            raise ValueError("Missing 'service' root key in YAML")

        service_data = yaml_data['service']

        # Parse required fields
        service_id = service_data.get('id')
        base_url = service_data.get('base_url')

        if not service_id:
            raise ValueError('Missing required field: service.id')
        if not base_url:
            raise ValueError('Missing required field: service.base_url')

        # Parse authentication config
        auth_config = ServiceDefinitionParser._parse_auth_config(
            service_data.get('auth', {})
        )

        # Parse API configs
        api_configs = ServiceDefinitionParser._parse_api_configs(
            service_data.get('apis', [])
        )

        return ServiceDefinition(
            id=service_id, base_url=base_url, auth=auth_config, apis=api_configs
        )

    @staticmethod
    def _parse_auth_config(auth_data: Dict[str, Any]) -> AuthConfig:
        """Parse authentication configuration."""
        auth_id = auth_data.get('id', 'default-auth')
        auth_type_str = auth_data.get('type', '').lower()

        # Validate auth type
        try:
            auth_type = AuthType(auth_type_str)
        except ValueError:
            raise ValueError(
                f'Invalid auth type: {auth_type_str}. Must be one of: {[t.value for t in AuthType]}'
            )

        auth_config = AuthConfig(
            id=auth_id,
            type=auth_type,
            version=auth_data.get('version', 'v1'),
            base_url=auth_data.get('base_url'),
            path=auth_data.get('path', ''),
            additional_headers=auth_data.get('additional_headers', {}),
        )

        # Set auth-specific fields based on type
        if auth_type == AuthType.BEARER:
            auth_config.token = auth_data.get('token')
            if not auth_config.token:
                raise ValueError("Bearer auth requires 'token' field")

        elif auth_type == AuthType.BASIC:
            auth_config.username = auth_data.get('username')
            auth_config.password = auth_data.get('password')
            if not auth_config.username or not auth_config.password:
                raise ValueError("Basic auth requires 'username' and 'password' fields")

        elif auth_type == AuthType.API_KEY:
            auth_config.api_key = auth_data.get('api_key')
            auth_config.api_key_header = auth_data.get('api_key_header', 'X-API-Key')
            if not auth_config.api_key:
                raise ValueError("API Key auth requires 'api_key' field")

        return auth_config

    @staticmethod
    def _parse_api_configs(apis_data: List[Dict[str, Any]]) -> List[ApiConfig]:
        """Parse API configurations."""
        api_configs = []

        for api_data in apis_data:
            api_id = api_data.get('id')
            # Exposed path (required)
            path = api_data.get('path')
            # Backend path (required)
            backend_path = api_data.get('backend_path')
            method_str = api_data.get('method', 'GET').upper()

            if not api_id:
                raise ValueError('API missing required field: id')
            if not path:
                raise ValueError(
                    f"API '{api_id}' missing required field: path (exposed)"
                )
            if not backend_path:
                raise ValueError(f"API '{api_id}' missing required field: backend_path")

            # Validate HTTP method
            try:
                method = HttpMethod(method_str)
            except ValueError:
                raise ValueError(
                    f'Invalid HTTP method: {method_str}. Must be one of: {[m.value for m in HttpMethod]}'
                )

            api_config = ApiConfig(
                id=api_id,
                path=path,
                backend_path=backend_path,
                method=method,
                version=api_data.get('version', 'v1'),
                additional_headers=api_data.get('additional_headers', {}),
                output_mapper_enabled=api_data.get('output_mapper', {}).get(
                    'enabled', False
                ),
                output_mapper=api_data.get('output_mapper', {}).get('mapper', {}),
            )

            api_configs.append(api_config)

        return api_configs
