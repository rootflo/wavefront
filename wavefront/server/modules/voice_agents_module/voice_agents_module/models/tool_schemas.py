from pydantic import BaseModel, Field, field_validator
from typing import Optional, Union, Any, Dict
from enum import Enum
from datetime import datetime
import uuid
import re
import ipaddress
from urllib.parse import urlparse

# Sentinel value for partial updates
UNSET = object()


class ToolType(str, Enum):
    API = 'api'
    PYTHON = 'python'


class AuthType(str, Enum):
    NONE = 'none'
    BEARER = 'bearer'
    API_KEY = 'api_key'
    BASIC = 'basic'


class ApiToolConfig(BaseModel):
    """Configuration for API-type tools"""

    method: str = Field(..., description='HTTP method (GET, POST, PUT, PATCH, DELETE)')
    url: str = Field(..., description='API endpoint URL')
    headers: Optional[Dict[str, str]] = Field(
        default=None, description='HTTP headers to include'
    )
    timeout: int = Field(
        default=30, ge=1, le=300, description='Request timeout in seconds'
    )
    auth_type: Optional[str] = Field(
        default='none', description='Authentication type (none, bearer, api_key)'
    )
    auth_credentials: Optional[Dict[str, str]] = Field(
        default=None, description='Authentication credentials'
    )

    @field_validator('method')
    @classmethod
    def validate_method(cls, v):
        allowed_methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']
        if v.upper() not in allowed_methods:
            raise ValueError(f'Method must be one of {allowed_methods}')
        return v.upper()

    @field_validator('url')
    @classmethod
    def validate_url(cls, v):
        parsed = urlparse(v)
        if parsed.scheme not in {'http', 'https'}:
            raise ValueError('URL must start with http:// or https://')
        host = parsed.hostname
        if not host:
            raise ValueError('URL must include a hostname')
        if host in {'localhost'}:
            raise ValueError('Cannot use localhost or internal IP addresses')
        try:
            ip = ipaddress.ip_address(host)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
            ):
                raise ValueError('Cannot use localhost or internal IP addresses')
        except ValueError:
            # Non-IP hostnames are allowed (optionally add DNS-based checks)
            pass
        return v

    @field_validator('auth_type')
    @classmethod
    def validate_auth_type(cls, v):
        if v and v not in ['none', 'bearer', 'api_key', 'basic']:
            raise ValueError('auth_type must be none, bearer, api_key, or basic')
        return v


class PythonToolConfig(BaseModel):
    """Configuration for Python-type tools (Phase 2)"""

    code_storage_key: str = Field(..., description='Cloud Storage key for Python code')
    cloud_run_url: str = Field(..., description='Cloud Run service URL')
    timeout: int = Field(
        default=60, ge=1, le=300, description='Execution timeout in seconds'
    )
    resource_limits: Optional[Dict[str, Any]] = Field(
        default=None, description='CPU and memory limits'
    )


class CreateToolPayload(BaseModel):
    """Payload for creating a new tool"""

    model_config = {'use_enum_values': True}

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description='Function identifier (lowercase with underscores)',
    )
    display_name: str = Field(
        ..., min_length=1, max_length=255, description='Human-readable name'
    )
    description: str = Field(
        ..., min_length=1, description='Description for LLM to decide when to call'
    )
    tool_type: ToolType = Field(..., description='Type of tool (api or python)')
    config: Dict[str, Any] = Field(..., description='Tool-specific configuration')
    parameter_schema: Optional[Dict[str, Any]] = Field(
        default=None, description='JSON Schema for parameter validation'
    )
    response_template: Optional[str] = Field(
        default=None, description='Template for formatting responses'
    )
    created_by: Optional[uuid.UUID] = Field(
        default=None, description='User who created the tool'
    )

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        # Python function naming convention
        if not re.match(r'^[a-z_][a-z0-9_]*$', v):
            raise ValueError(
                'Name must follow Python function naming: lowercase letters, numbers, underscores only, cannot start with number'
            )
        return v

    @field_validator('config')
    @classmethod
    def validate_config(cls, v, info):
        # Validate config structure based on tool_type
        tool_type = info.data.get('tool_type')
        # Handle both enum and string values
        tool_type_value = (
            tool_type
            if isinstance(tool_type, str)
            else (tool_type.value if tool_type else None)
        )

        if tool_type_value == 'api':
            # Validate as ApiToolConfig
            try:
                ApiToolConfig(**v)
            except Exception as e:
                raise ValueError(f'Invalid API tool config: {str(e)}')
        elif tool_type_value == 'python':
            # Validate as PythonToolConfig (Phase 2)
            try:
                PythonToolConfig(**v)
            except Exception as e:
                raise ValueError(f'Invalid Python tool config: {str(e)}')
        return v

    @field_validator('parameter_schema')
    @classmethod
    def validate_parameter_schema(cls, v):
        if v is None:
            return v

        # Validate that it's a proper JSON Schema
        if not isinstance(v, dict):
            raise ValueError('parameter_schema must be a JSON object')

        # Check for required JSON Schema fields
        if 'type' not in v:
            raise ValueError(
                'parameter_schema must have a "type" field (usually "object")'
            )

        if v.get('type') == 'object':
            if 'properties' not in v:
                raise ValueError(
                    'parameter_schema with type "object" must have a "properties" field'
                )

            # Validate that properties is a dict
            if not isinstance(v['properties'], dict):
                raise ValueError('parameter_schema "properties" must be an object')

        return v


class UpdateToolPayload(BaseModel):
    """Payload for updating a tool (partial updates)"""

    name: Union[str, Any] = Field(default=UNSET)
    display_name: Union[str, Any] = Field(default=UNSET)
    description: Union[str, Any] = Field(default=UNSET)
    tool_type: Union[ToolType, Any] = Field(default=UNSET)
    config: Union[Dict[str, Any], Any] = Field(default=UNSET)
    parameter_schema: Union[Dict[str, Any], None, Any] = Field(default=UNSET)
    response_template: Union[str, None, Any] = Field(default=UNSET)

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if v is UNSET:
            return v
        if not re.match(r'^[a-z_][a-z0-9_]*$', v):
            raise ValueError(
                'Name must follow Python function naming: lowercase letters, numbers, underscores only'
            )
        return v

    @field_validator('config')
    @classmethod
    def validate_config(cls, v, info):
        """
        Validate config structure when both config and tool_type are provided.
        Note: Service-level validation handles cases where only config is updated.
        """
        if v is UNSET:
            return v

        # Only validate if tool_type is also provided in this update
        tool_type = info.data.get('tool_type')
        if tool_type is UNSET or tool_type is None:
            # Config will be validated at service layer against existing tool_type
            return v

        # Handle both enum and string values
        tool_type_value = (
            tool_type
            if isinstance(tool_type, str)
            else (tool_type.value if tool_type else None)
        )

        if tool_type_value == 'api':
            # Validate as ApiToolConfig
            try:
                ApiToolConfig(**v)
            except Exception as e:
                raise ValueError(f'Invalid API tool config: {str(e)}')
        elif tool_type_value == 'python':
            # Validate as PythonToolConfig
            try:
                PythonToolConfig(**v)
            except Exception as e:
                raise ValueError(f'Invalid Python tool config: {str(e)}')
        return v

    @field_validator('parameter_schema')
    @classmethod
    def validate_parameter_schema(cls, v):
        if v is UNSET or v is None:
            return v

        # Validate that it's a proper JSON Schema
        if not isinstance(v, dict):
            raise ValueError('parameter_schema must be a JSON object')

        # Check for required JSON Schema fields
        if 'type' not in v:
            raise ValueError(
                'parameter_schema must have a "type" field (usually "object")'
            )

        if v.get('type') == 'object':
            if 'properties' not in v:
                raise ValueError(
                    'parameter_schema with type "object" must have a "properties" field'
                )

            # Validate that properties is a dict
            if not isinstance(v['properties'], dict):
                raise ValueError('parameter_schema "properties" must be an object')

        return v


class AttachToolToAgentPayload(BaseModel):
    """Payload for attaching a tool to a voice agent"""

    tool_id: uuid.UUID = Field(..., description='ID of the tool to attach')
    is_enabled: bool = Field(default=True, description='Enable/disable the tool')
    config_overrides: Optional[Dict[str, Any]] = Field(
        default=None, description='Agent-specific config overrides'
    )
    priority: int = Field(
        default=0, description='Execution priority (higher = earlier)'
    )


class UpdateAgentToolPayload(BaseModel):
    """Payload for updating a tool association"""

    is_enabled: Union[bool, Any] = Field(default=UNSET)
    config_overrides: Union[Dict[str, Any], None, Any] = Field(default=UNSET)
    priority: Union[int, Any] = Field(default=UNSET)


class ToolResponse(BaseModel):
    """Response model for tool data"""

    id: uuid.UUID
    name: str
    display_name: str
    description: str
    tool_type: str
    config: Dict[str, Any]
    parameter_schema: Optional[Dict[str, Any]]
    response_template: Optional[str]
    created_by: Optional[uuid.UUID]
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AgentToolResponse(BaseModel):
    """Response model for agent-tool association"""

    id: uuid.UUID
    voice_agent_id: uuid.UUID
    tool_id: uuid.UUID
    is_enabled: bool
    config_overrides: Optional[Dict[str, Any]]
    priority: int
    created_at: datetime
    updated_at: datetime
    # Include tool details
    tool: Optional[ToolResponse] = None

    class Config:
        from_attributes = True
