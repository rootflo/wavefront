"""Service definition models."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class AuthType(Enum):
    """Supported authentication types."""

    BEARER = 'bearer'
    BASIC = 'basic'
    API_KEY = 'api_key'


class HttpMethod(Enum):
    """Supported HTTP methods."""

    GET = 'GET'
    POST = 'POST'
    PUT = 'PUT'
    DELETE = 'DELETE'
    PATCH = 'PATCH'


@dataclass
class PayloadFieldSchema:
    """Schema definition for a single payload field."""

    name: str
    type: str  # string, integer, number, boolean, array, object
    required: bool = False
    description: str = ''


@dataclass
class PayloadSchema:
    """Complete payload schema definition."""

    fields: List['PayloadFieldSchema'] = field(default_factory=list)


@dataclass
class AuthConfig:
    """Authentication configuration."""

    id: str
    type: AuthType
    version: str = 'v1'
    base_url: Optional[str] = None
    path: str = ''
    additional_headers: Dict[str, str] = field(default_factory=dict)

    # Auth type-specific configurations
    token: Optional[str] = None  # For bearer auth
    username: Optional[str] = None  # For basic auth
    password: Optional[str] = None  # For basic auth
    api_key: Optional[str] = None  # For API key auth
    api_key_header: str = 'X-API-Key'  # Header name for API key


@dataclass
class ApiConfig:
    """API endpoint configuration."""

    id: str
    # Exposed proxy path (e.g., /get-objects or /get-objects/{id})
    path: str
    # Backend path template (e.g., /objects or /objects/{id})
    backend_path: str
    method: HttpMethod
    version: str = 'v1'
    description: str = ''
    additional_headers: Dict[str, str] = field(default_factory=dict)
    # Backend query parameters to be sent with the request
    backend_query_params: Dict[str, Any] = field(default_factory=dict)

    # Output mapping configuration (simplified for Phase 1)
    output_mapper_enabled: bool = False
    output_mapper: Dict[str, str] = field(default_factory=dict)

    # Payload validation schema (for POST/PUT/PATCH requests)
    payload_schema: Optional['PayloadSchema'] = None


@dataclass
class ServiceDefinition:
    """Complete service definition."""

    id: str
    base_url: str
    auth: AuthConfig
    apis: List[ApiConfig] = field(default_factory=list)

    def get_api_by_id(self, api_id: str, version: str = 'v1') -> Optional[ApiConfig]:
        """Get API configuration by ID and version."""
        for api in self.apis:
            if api.id == api_id and api.version == version:
                return api
        return None

    def get_api_ids(self) -> List[str]:
        """Get list of all API IDs."""
        return [api.id for api in self.apis]


@dataclass
class ProxyResponse:
    """Standardized proxy response."""

    meta: Dict[str, Any]
    data: Any
    http_status_code: int = 200

    @classmethod
    def success(
        cls,
        data: Any,
        trace: Optional[List[str]] = None,
        message: str = 'Success',
        http_status_code: int = 200,
    ) -> 'ProxyResponse':
        """Create a successful response."""
        return cls(
            meta={'status': 'success', 'message': message, 'trace': trace},
            data=data,
            http_status_code=http_status_code,
        )

    @classmethod
    def error(
        cls,
        message: str,
        trace: Optional[List[str]] = None,
        status: str = 'error',
        http_status_code: int = 500,
    ) -> 'ProxyResponse':
        """Create an error response."""
        return cls(
            meta={'status': status, 'message': message, 'trace': trace},
            data=None,
            http_status_code=http_status_code,
        )
