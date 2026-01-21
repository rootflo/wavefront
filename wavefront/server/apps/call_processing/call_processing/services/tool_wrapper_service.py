"""
Tool Wrapper Service for executing tools during voice agent calls.

This service provides wrapper classes and a factory for creating Pipecat-compatible
functions that can be registered with the LLM for function calling.
"""

import base64
from typing import Dict, Any, List, Tuple, Callable, Optional
import httpx

from call_processing.log.logger import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema


class ApiToolWrapper:
    """Wrapper for API-based tools that makes HTTP requests"""

    def __init__(
        self,
        url: str,
        method: str,
        headers: Optional[Dict[str, str]] = None,
        auth_type: Optional[str] = None,
        auth_credentials: Optional[Dict[str, str]] = None,
        timeout: int = 30,
    ):
        """
        Initialize API tool wrapper

        Args:
            url: API endpoint URL
            method: HTTP method (GET, POST, PUT, PATCH, DELETE)
            headers: HTTP headers to include
            auth_type: Authentication type (none, bearer, api_key, basic)
            auth_credentials: Authentication credentials
            timeout: Request timeout in seconds
        """
        self.url = url
        self.method = method.upper()
        self.headers = headers or {}
        self.auth_type = auth_type or 'none'
        self.auth_credentials = auth_credentials or {}
        self.timeout = timeout

    def _apply_auth(self, headers: Dict[str, str]) -> Dict[str, str]:
        """
        Apply authentication to headers

        Args:
            headers: Base headers dictionary

        Returns:
            Headers with authentication applied
        """
        if self.auth_type == 'bearer':
            token = self.auth_credentials.get('token')
            if token:
                headers['Authorization'] = f'Bearer {token}'
        elif self.auth_type == 'api_key':
            key_name = self.auth_credentials.get('key_name', 'X-API-Key')
            key_value = self.auth_credentials.get('key_value')
            if key_value:
                headers[key_name] = key_value
        elif self.auth_type == 'basic':
            username = self.auth_credentials.get('username')
            password = self.auth_credentials.get('password')
            if username and password:
                # Encode credentials as base64
                credentials = f'{username}:{password}'
                encoded = base64.b64encode(credentials.encode()).decode()
                headers['Authorization'] = f'Basic {encoded}'
        return headers

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the API call

        Args:
            params: Parameters provided by LLM

        Returns:
            Structured response dictionary with:
            - success (bool): Whether the API call succeeded
            - status_code (int): HTTP status code
            - data (dict): Response body (if successful)
            - error (str): Error message (if failed)
        """
        try:
            # Apply authentication
            headers = self._apply_auth(self.headers.copy())

            # Make HTTP request
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if self.method == 'GET':
                    response = await client.get(
                        self.url, params=params, headers=headers
                    )
                elif self.method in ['POST', 'PUT', 'PATCH']:
                    response = await client.request(
                        self.method, self.url, json=params, headers=headers
                    )
                elif self.method == 'DELETE':
                    response = await client.delete(self.url, headers=headers)
                else:
                    return {
                        'success': False,
                        'error': f'Unsupported HTTP method: {self.method}',
                        'status_code': 400,
                    }

                # Parse response
                response.raise_for_status()
                try:
                    data = response.json()
                except Exception:
                    data = {'raw': response.text}

                return data

        except httpx.TimeoutException as e:
            logger.warning(f'API tool timeout for {self.url}: {str(e)}')
            return {'success': False, 'error': 'Request timeout', 'status_code': 408}
        except httpx.HTTPStatusError as e:
            logger.warning(
                f'API tool HTTP error for {self.url}: {e.response.status_code}'
            )
            return {
                'success': False,
                'error': f'HTTP error: {e.response.status_code}',
                'status_code': e.response.status_code,
            }
        except Exception as e:
            logger.error(f'API tool unexpected error for {self.url}: {str(e)}')
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'status_code': 500,
            }


class PythonToolWrapper:
    """Wrapper for Python code tools (Phase 2 - stub implementation)"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Python tool wrapper

        Args:
            config: Python tool configuration
        """
        self.config = config
        logger.info('PythonToolWrapper initialized (Phase 2 - not yet implemented)')

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute Python code (stub - Phase 2)

        Args:
            params: Parameters provided by LLM

        Returns:
            Error response indicating not implemented
        """
        logger.warning('Python tool execution attempted but not yet implemented')
        return {
            'success': False,
            'error': 'Python tool execution not yet implemented (Phase 2)',
            'status_code': 501,
        }


class ToolWrapperFactory:
    """Factory for creating tool wrapper instances and Pipecat-compatible functions"""

    @staticmethod
    def create_wrapper(tool: Dict[str, Any]):
        """
        Create appropriate wrapper based on tool type

        Args:
            tool: Tool configuration dictionary

        Returns:
            ApiToolWrapper or PythonToolWrapper instance

        Raises:
            ValueError: If tool type is unsupported
        """
        tool_type = tool.get('tool_type')
        config = tool.get('config', {})

        if tool_type == 'api':
            return ApiToolWrapper(
                url=config.get('url'),
                method=config.get('method', 'POST'),
                headers=config.get('headers', {}),
                auth_type=config.get('auth_type', 'none'),
                auth_credentials=config.get('auth_credentials', {}),
                timeout=config.get('timeout', 30),
            )
        elif tool_type == 'python':
            return PythonToolWrapper(config)
        else:
            raise ValueError(f'Unsupported tool type: {tool_type}')

    @staticmethod
    def create_pipecat_function(
        tool: Dict[str, Any], wrapper
    ) -> Tuple[FunctionSchema, Callable]:
        """
        Create a Pipecat FunctionSchema and callable function for a tool

        Args:
            tool: Tool configuration dictionary
            wrapper: Tool wrapper instance (ApiToolWrapper or PythonToolWrapper)

        Returns:
            Tuple of (FunctionSchema, callable_function)
            - FunctionSchema: For passing to ToolsSchema
            - callable_function: For registering with llm.register_function()
        """
        tool_name = tool.get('name')
        tool_description = tool.get('description')
        parameter_schema = tool.get('parameter_schema', {}) or {}

        # Extract properties and required fields from parameter_schema
        properties = parameter_schema.get('properties', {})
        required = parameter_schema.get('required', [])

        # Create FunctionSchema object (Pipecat's official way)
        function_schema = FunctionSchema(
            name=tool_name,
            description=tool_description,
            properties=properties,
            required=required,
        )

        async def tool_function(params):
            """
            Generated function for Pipecat integration

            This function is called by Pipecat when the LLM decides to invoke the tool.
            It executes the tool wrapper and returns results to the LLM.
            """
            try:
                logger.info(
                    f"Executing tool '{tool_name}' with params: {params.arguments if hasattr(params, 'arguments') else params}"
                )

                # Handle different parameter formats from Pipecat
                if hasattr(params, 'arguments'):
                    # FunctionCallParams object
                    tool_params = params.arguments
                    result_callback = params.result_callback
                else:
                    # Direct dict parameters
                    tool_params = params
                    result_callback = None

                # Execute the tool wrapper
                result = await wrapper.execute(tool_params)

                logger.info(f"Tool '{tool_name}' execution result: {result}")

                # Return result via callback if available
                if result_callback:
                    await result_callback(result)

                return result

            except Exception as e:
                error_msg = f"Error executing tool '{tool_name}': {str(e)}"
                logger.error(error_msg)
                error_result = {
                    'success': False,
                    'error': error_msg,
                    'status_code': 500,
                }

                if result_callback:
                    await result_callback(error_result)

                return error_result

        # Set function metadata for Pipecat
        tool_function.__name__ = tool_name
        tool_function.__doc__ = tool_description

        return function_schema, tool_function

    @staticmethod
    def create_all_tool_functions(
        agent_tools: List[Dict[str, Any]],
    ) -> Tuple[List[FunctionSchema], List[Tuple[str, Callable]]]:
        """
        Create wrapper functions for all tools attached to an agent

        Args:
            agent_tools: List of tool configurations from get_agent_tools()
                        Each dict contains: {id, name, description, tool_type,
                                            config, parameter_schema, is_enabled, association}

        Returns:
            Tuple containing:
            - function_schemas: List of FunctionSchema objects (for ToolsSchema)
            - tool_registrations: List of (name, callable) tuples (for llm.register_function)
        """
        function_schemas = []
        tool_registrations = []

        # Filter to only enabled tools
        enabled_tools = [
            t for t in agent_tools if t.get('association', {}).get('is_enabled', True)
        ]

        logger.info(
            f'Creating wrapper functions for {len(enabled_tools)} enabled tools'
        )

        for tool in enabled_tools:
            try:
                # Create wrapper based on tool type
                wrapper = ToolWrapperFactory.create_wrapper(tool)

                # Apply config overrides if present
                config_overrides = tool.get('association', {}).get('config_overrides')
                if config_overrides:
                    if isinstance(wrapper, ApiToolWrapper):
                        # For ApiToolWrapper, set attributes directly
                        allowed_attrs = {
                            'url',
                            'method',
                            'headers',
                            'auth_type',
                            'auth_credentials',
                            'timeout',
                        }
                        for key, value in config_overrides.items():
                            if key in allowed_attrs:
                                if hasattr(wrapper, key):
                                    setattr(wrapper, key, value)
                                    logger.debug(
                                        f"Applied config override for tool '{tool['name']}': {key}={value}"
                                    )
                            else:
                                logger.debug(
                                    f"Ignoring unknown config override key for tool '{tool['name']}': {key}"
                                )
                    elif hasattr(wrapper, 'config'):
                        # For wrappers with config dict (e.g., PythonToolWrapper)
                        wrapper.config.update(config_overrides)
                        logger.debug(
                            f"Applied config overrides for tool '{tool['name']}': {config_overrides}"
                        )

                # Create Pipecat FunctionSchema and callable function
                function_schema, callable_func = (
                    ToolWrapperFactory.create_pipecat_function(tool, wrapper)
                )

                # Add to both lists
                function_schemas.append(function_schema)
                tool_registrations.append((tool['name'], callable_func))

                logger.info(
                    f"Created wrapper for tool '{tool['name']}' (type: {tool['tool_type']})"
                )

            except Exception as e:
                logger.error(
                    f"Error creating wrapper for tool '{tool.get('name')}': {str(e)}"
                )
                # Skip this tool but continue with others
                continue

        logger.info(
            f'Successfully created {len(function_schemas)} tool wrapper functions'
        )

        return function_schemas, tool_registrations
