"""Concrete pipeline stages for API processing."""

import asyncio
import httpx
from typing import Dict, Any, Optional
from urllib.parse import urljoin

from ..models.pipeline import (
    PipelineStage,
    PipelineContext,
    StageType,
    PipelineException,
)
from ..models.service import ApiConfig, ServiceDefinition


class RequestHeadersForwarderStage(PipelineStage):
    """Pipeline stage for forwarding incoming request headers to backend."""

    # Headers that should NOT be forwarded to the backend
    # Includes hop-by-hop headers and authentication headers
    EXCLUDED_HEADERS = {
        # Hop-by-hop headers (should not be forwarded)
        'host',
        'content-length',
        'transfer-encoding',
        'connection',
        'keep-alive',
        'proxy-authenticate',
        'proxy-authorization',
        'te',
        'trailers',
        'upgrade',
        # Authentication headers (will be set by auth pipeline)
        'authorization',
        'x-api-key',
        'api-key',
        'x-auth-token',
        'cookie',
        'set-cookie',
        'x-client-key',
    }

    def __init__(self):
        pass

    async def execute(self, context: PipelineContext) -> PipelineContext:
        """Forward incoming request headers to backend headers."""
        context.add_trace(
            self.get_name(), f'Forwarding {len(context.headers)} incoming headers'
        )

        try:
            # Filter and forward headers
            forwarded_count = 0
            for header_name, header_value in context.headers.items():
                # Skip excluded headers
                if header_name.lower() in self.EXCLUDED_HEADERS:
                    continue

                # Forward the header to backend
                context.backend_headers[header_name] = header_value
                forwarded_count += 1

            context.add_trace(
                self.get_name(), f'Forwarded {forwarded_count} headers to backend'
            )
            return context

        except Exception as e:
            context.add_trace(self.get_name(), f'Header forwarding failed: {str(e)}')
            raise PipelineException(
                f'Header forwarding failed: {str(e)}', self.get_name(), context
            )

    def get_stage_type(self) -> StageType:
        """Return header forwarder stage type."""
        return StageType.HEADER_INJECTOR

    def get_name(self) -> str:
        """Return stage name."""
        return 'request_headers_forwarder'


class HeaderInjectorStage(PipelineStage):
    """Pipeline stage for injecting additional headers."""

    def __init__(self, headers: Dict[str, str], stage_name: str = 'header_injector'):
        self.headers = headers
        self.stage_name = stage_name

    async def execute(self, context: PipelineContext) -> PipelineContext:
        """Inject additional headers into the context."""
        context.add_trace(self.get_name(), f'Injecting {len(self.headers)} headers')

        try:
            context.merge_backend_headers(self.headers)
            context.add_trace(self.get_name(), 'Headers injected successfully')
            return context

        except Exception as e:
            context.add_trace(self.get_name(), f'Header injection failed: {str(e)}')
            raise PipelineException(
                f'Header injection failed: {str(e)}', self.get_name(), context
            )

    def get_stage_type(self) -> StageType:
        """Return header injector stage type."""
        return StageType.HEADER_INJECTOR

    def get_name(self) -> str:
        """Return stage name."""
        return self.stage_name


class ApiProcessorStage(PipelineStage):
    """Pipeline stage for processing API configuration."""

    def __init__(self, api_config: ApiConfig, service_definition: ServiceDefinition):
        self.api_config = api_config
        self.service_definition = service_definition

    async def execute(self, context: PipelineContext) -> PipelineContext:
        """Process API configuration and prepare backend request."""
        context.add_trace(self.get_name(), f'Processing API: {self.api_config.id}')

        try:
            # Set backend URL and path
            context.backend_url = self.service_definition.base_url
            context.backend_path = self._substitute_path_parameters(
                self.api_config.backend_path, context.path_params
            )

            # Add API-specific headers
            context.merge_backend_headers(self.api_config.additional_headers)

            # Merge backend query params (backend config params first, then incoming params can override)
            if self.api_config.backend_query_params:
                merged_params = dict(self.api_config.backend_query_params)
                merged_params.update(context.query_params)
                context.query_params = merged_params
                context.add_trace(
                    self.get_name(),
                    f'Merged {len(self.api_config.backend_query_params)} backend query params',
                )

            # Store API config in context for later stages
            context.auth_config.update(
                {
                    'api_id': self.api_config.id,
                    'api_version': self.api_config.version,
                    'api_method': self.api_config.method.value,
                }
            )

            context.add_trace(
                self.get_name(), f'API processing completed for {self.api_config.id}'
            )
            return context

        except Exception as e:
            context.add_trace(self.get_name(), f'API processing failed: {str(e)}')
            raise PipelineException(
                f'API processing failed: {str(e)}', self.get_name(), context
            )

    def get_stage_type(self) -> StageType:
        """Return API processor stage type."""
        return StageType.API_PROCESSOR

    def get_name(self) -> str:
        """Return stage name."""
        return f'api_processor_{self.api_config.id}'

    def _substitute_path_parameters(
        self, path_template: str, path_params: Dict[str, str]
    ) -> str:
        """
        Substitute path parameters in the path template.

        Args:
            path_template: Path template with parameters like /users/{id}/orders
            path_params: Dictionary of parameter values

        Returns:
            Path with parameters substituted
        """
        result_path = path_template
        for param_name, param_value in path_params.items():
            result_path = result_path.replace(f'{{{param_name}}}', param_value)
        return result_path


class RequestSenderStage(PipelineStage):
    """Pipeline stage for sending requests to backend services."""

    def __init__(self, timeout: int = 30, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries

    async def execute(self, context: PipelineContext) -> PipelineContext:
        """Send request to backend service."""
        context.add_trace(self.get_name(), f'Sending request to {context.backend_url}')

        try:
            # Construct full URL
            full_url = urljoin(
                context.backend_url.rstrip('/') + '/', context.backend_path.lstrip('/')
            )

            # Get method from API config or default to POST
            method = context.auth_config.get('api_method', 'POST')

            # Prepare request parameters
            request_params = {
                'method': method,
                'url': full_url,
                'headers': context.backend_headers,
                'params': context.query_params,
                'timeout': self.timeout,
            }

            # Add body for methods that support it
            if method in ['POST', 'PUT', 'PATCH'] and context.body is not None:
                if isinstance(context.body, dict):
                    request_params['json'] = context.body
                else:
                    request_params['content'] = context.body

            # Send request with retry logic
            response = await self._send_with_retry(request_params)

            # Store response in context
            context.response_status = response.status_code
            context.response_headers = dict(response.headers)

            # Check if response is binary content
            content_type = response.headers.get('content-type', '').lower()
            is_binary = self._is_binary_content_type(content_type)

            if is_binary:
                # Store raw bytes for binary content
                context.is_binary_response = True
                context.raw_response_content = response.content
                context.response_body = None  # Don't parse binary as JSON/text
                context.add_trace(
                    self.get_name(),
                    f'Received binary response ({content_type}), size: {len(response.content)} bytes',
                )
            else:
                # Parse response body for text/json content
                try:
                    context.response_body = response.json()
                except Exception:
                    context.response_body = response.text

            context.add_trace(
                self.get_name(), f'Request completed with status {response.status_code}'
            )
            return context

        except Exception as e:
            context.add_trace(self.get_name(), f'Request failed: {str(e)}')
            raise PipelineException(
                f'Backend request failed: {str(e)}', self.get_name(), context
            )

    async def _send_with_retry(self, request_params: Dict[str, Any]) -> httpx.Response:
        """Send request with retry logic using async httpx client."""
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.request(**request_params)

                    # Check status code - 4xx are valid responses, don't retry
                    # 5xx server errors should be retried
                    if 400 <= response.status_code < 500:
                        # Client error (4xx) - return as valid response, don't retry
                        return response
                    elif 500 <= response.status_code < 600:
                        # Server error (5xx) - raise to trigger retry
                        response.raise_for_status()
                    else:
                        # Success (2xx, 3xx) - return response
                        return response

            except httpx.HTTPStatusError as e:
                # Handle HTTPStatusError (from raise_for_status)
                if 400 <= e.response.status_code < 500:
                    # Client error (4xx) - return as valid response, don't retry
                    return e.response
                # Server error (5xx) - will retry
                last_exception = e

            except (httpx.RequestError, httpx.TimeoutException) as e:
                # Connection errors, timeouts, etc. - will retry
                last_exception = e

            # Wait before retry (exponential backoff using asyncio.sleep)
            if attempt < self.max_retries - 1 and last_exception is not None:
                await asyncio.sleep(2**attempt)

        # All retries failed
        if last_exception is not None:
            raise last_exception
        raise Exception('Request failed after all retries')

    def _is_binary_content_type(self, content_type: str) -> bool:
        """
        Check if content type indicates binary content.

        Args:
            content_type: Content-Type header value (already lowercased)

        Returns:
            True if binary content, False otherwise
        """
        # List of binary content type patterns
        binary_patterns = [
            'audio/',
            'video/',
            'image/',
            'application/octet-stream',
            'application/pdf',
            'application/zip',
            'application/x-tar',
            'application/x-gzip',
            'multipart/',
        ]

        # Check if any binary pattern matches
        for pattern in binary_patterns:
            if pattern in content_type:
                return True

        # Default to text/json for everything else
        return False

    def get_stage_type(self) -> StageType:
        """Return request sender stage type."""
        return StageType.REQUEST_SENDER

    def get_name(self) -> str:
        """Return stage name."""
        return 'request_sender'


class ResponseMapperStage(PipelineStage):
    """Pipeline stage for mapping response fields."""

    def __init__(self, api_config: ApiConfig):
        self.api_config = api_config

    async def execute(self, context: PipelineContext) -> PipelineContext:
        """Map response fields if output mapper is enabled."""
        context.add_trace(self.get_name(), 'Processing response mapping')

        try:
            if (
                not self.api_config.output_mapper_enabled
                or not self.api_config.output_mapper
            ):
                context.add_trace(
                    self.get_name(), 'No output mapping configured, skipping'
                )
                return context

            if not isinstance(context.response_body, dict):
                context.add_trace(
                    self.get_name(), 'Response body is not a dict, skipping mapping'
                )
                return context

            # Apply field mapping
            mapped_response = self._apply_field_mapping(
                context.response_body, self.api_config.output_mapper
            )

            context.response_body = mapped_response
            context.add_trace(
                self.get_name(),
                f'Applied {len(self.api_config.output_mapper)} field mappings',
            )
            return context

        except Exception as e:
            context.add_trace(self.get_name(), f'Response mapping failed: {str(e)}')
            raise PipelineException(
                f'Response mapping failed: {str(e)}', self.get_name(), context
            )

    def _apply_field_mapping(
        self, data: Dict[str, Any], mapping: Dict[str, str]
    ) -> Dict[str, Any]:
        """Apply field mapping to response data."""
        mapped_data = {}

        for source_path, target_path in mapping.items():
            try:
                # Get value from source path (supports dot notation)
                value = self._get_nested_value(data, source_path)

                # Set value at target path (supports dot notation)
                self._set_nested_value(mapped_data, target_path, value)

            except KeyError:
                # Source field doesn't exist, skip this mapping
                continue

        return mapped_data

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get value from nested dictionary using dot notation."""
        keys = path.split('.')
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                raise KeyError(f"Path '{path}' not found in data")

        return current

    def _set_nested_value(self, data: Dict[str, Any], path: str, value: Any):
        """Set value in nested dictionary using dot notation."""
        keys = path.split('.')
        current = data

        # Navigate to the parent of the target key
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        # Set the final value
        current[keys[-1]] = value

    def get_stage_type(self) -> StageType:
        """Return response mapper stage type."""
        return StageType.RESPONSE_MAPPER

    def get_name(self) -> str:
        """Return stage name."""
        return f'response_mapper_{self.api_config.id}'


class PayloadValidatorStage(PipelineStage):
    """Pipeline stage for validating request payload against schema."""

    def __init__(self, api_config: ApiConfig):
        self.api_config = api_config

    async def execute(self, context: PipelineContext) -> PipelineContext:
        """Validate request payload against schema."""
        context.add_trace(self.get_name(), 'Starting payload validation')

        try:
            # Skip validation if no schema defined
            if not self.api_config.payload_schema:
                context.add_trace(
                    self.get_name(), 'No payload schema defined, skipping validation'
                )
                return context

            # Skip validation if method is not POST/PUT/PATCH
            method = context.method.upper()
            if method not in ['POST', 'PUT', 'PATCH']:
                context.add_trace(
                    self.get_name(),
                    f'Method {method} does not require payload validation, skipping',
                )
                return context

            # Skip validation if no body provided
            if context.body is None:
                context.add_trace(self.get_name(), 'No request body provided')
                # Check if there are required fields
                required_fields = [
                    f.name for f in self.api_config.payload_schema.fields if f.required
                ]
                if required_fields:
                    error_msg = f"Missing required fields: {', '.join(required_fields)}"
                    context.add_trace(
                        self.get_name(), f'Validation failed: {error_msg}'
                    )
                    raise PipelineException(
                        f'Payload validation failed: {error_msg}',
                        self.get_name(),
                        context,
                    )
                return context

            # Validate payload
            validation_errors = self._validate_payload(
                context.body, self.api_config.payload_schema
            )

            if validation_errors:
                error_msg = '; '.join(validation_errors)
                context.add_trace(self.get_name(), f'Validation failed: {error_msg}')
                raise PipelineException(
                    f'Payload validation failed: {error_msg}', self.get_name(), context
                )

            context.add_trace(
                self.get_name(),
                f'Payload validation completed successfully ({len(self.api_config.payload_schema.fields)} fields checked)',
            )
            return context

        except PipelineException:
            # Re-raise pipeline exceptions
            raise
        except Exception as e:
            context.add_trace(self.get_name(), f'Payload validation error: {str(e)}')
            raise PipelineException(
                f'Payload validation error: {str(e)}', self.get_name(), context
            )

    def _validate_payload(self, payload: Any, schema) -> list:
        """
        Validate payload against schema.

        Args:
            payload: Request payload (should be dict)
            schema: PayloadSchema object

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Payload must be a dictionary
        if not isinstance(payload, dict):
            errors.append(
                f'Payload must be an object/dictionary, got {type(payload).__name__}'
            )
            return errors

        # Check each field in schema
        for field_schema in schema.fields:
            field_name = field_schema.name
            field_type = field_schema.type
            required = field_schema.required

            # Check if field exists
            if field_name not in payload or payload[field_name] is None:
                if required:
                    errors.append(f"Missing required field '{field_name}'")
                continue

            # Validate field type
            value = payload[field_name]
            type_error = self._validate_field_type(value, field_type, field_name)
            if type_error:
                errors.append(type_error)

        return errors

    def _validate_field_type(
        self, value: Any, expected_type: str, field_name: str
    ) -> Optional[str]:
        """
        Validate individual field type.

        Args:
            value: Field value to validate
            expected_type: Expected type (string, integer, number, boolean, array, object)
            field_name: Name of the field (for error messages)

        Returns:
            Error message if invalid, None if valid
        """
        actual_type = type(value).__name__

        if expected_type == 'string':
            if not isinstance(value, str):
                return (
                    f"Field '{field_name}' expected type string but got {actual_type}"
                )

        elif expected_type == 'integer':
            # Must be int, not float (even if float is a whole number)
            if not isinstance(value, int) or isinstance(value, bool):
                return (
                    f"Field '{field_name}' expected type integer but got {actual_type}"
                )

        elif expected_type == 'number':
            # Can be int or float
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return (
                    f"Field '{field_name}' expected type number but got {actual_type}"
                )

        elif expected_type == 'boolean':
            if not isinstance(value, bool):
                return (
                    f"Field '{field_name}' expected type boolean but got {actual_type}"
                )

        elif expected_type == 'array':
            if not isinstance(value, list):
                return f"Field '{field_name}' expected type array but got {actual_type}"

        elif expected_type == 'object':
            if not isinstance(value, dict):
                return (
                    f"Field '{field_name}' expected type object but got {actual_type}"
                )

        else:
            return f"Field '{field_name}' has unknown type '{expected_type}'"

        return None

    def get_stage_type(self) -> StageType:
        """Return payload validator stage type."""
        return StageType.PAYLOAD_VALIDATOR

    def get_name(self) -> str:
        """Return stage name."""
        return f'payload_validator_{self.api_config.id}'
