"""Authentication handlers for different auth types."""

import base64
from typing import Dict
from abc import abstractmethod

from ..models.pipeline import (
    PipelineStage,
    PipelineContext,
    StageType,
    PipelineException,
)
from ..models.service import AuthType, AuthConfig


class AuthHandler(PipelineStage):
    """Base class for authentication handlers."""

    def __init__(self, auth_config: AuthConfig):
        self.auth_config = auth_config

    def get_stage_type(self) -> StageType:
        """Return authenticator stage type."""
        return StageType.AUTHENTICATOR

    def get_name(self) -> str:
        """Return the authenticator name."""
        return f'{self.auth_config.type.value}_authenticator'

    @abstractmethod
    def generate_auth_headers(self, context: PipelineContext) -> Dict[str, str]:
        """Generate authentication headers based on auth type."""
        pass

    async def execute(self, context: PipelineContext) -> PipelineContext:
        """Execute authentication stage."""
        context.add_trace(
            self.get_name(), f'Starting {self.auth_config.type.value} authentication'
        )

        try:
            # Generate auth-specific headers
            auth_headers = self.generate_auth_headers(context)

            # Add additional headers from config
            auth_headers.update(self.auth_config.additional_headers)

            # Store auth headers in context
            context.auth_headers.update(auth_headers)
            context.merge_backend_headers(auth_headers)

            context.add_trace(
                self.get_name(), 'Authentication headers generated successfully'
            )
            return context

        except Exception as e:
            context.add_trace(self.get_name(), f'Authentication failed: {str(e)}')
            raise PipelineException(
                f'Authentication failed: {str(e)}', self.get_name(), context
            )


class BearerAuthHandler(AuthHandler):
    """Bearer token authentication handler."""

    def __init__(self, auth_config: AuthConfig):
        super().__init__(auth_config)
        if not auth_config.token:
            raise ValueError('Bearer auth requires a token')

    def generate_auth_headers(self, context: PipelineContext) -> Dict[str, str]:
        """Generate Bearer token headers."""
        return {'Authorization': f'Bearer {self.auth_config.token}'}


class BasicAuthHandler(AuthHandler):
    """Basic authentication handler."""

    def __init__(self, auth_config: AuthConfig):
        super().__init__(auth_config)
        if not auth_config.username or not auth_config.password:
            raise ValueError('Basic auth requires username and password')

    def generate_auth_headers(self, context: PipelineContext) -> Dict[str, str]:
        """Generate Basic auth headers."""
        credentials = f'{self.auth_config.username}:{self.auth_config.password}'
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        return {'Authorization': f'Basic {encoded_credentials}'}


class ApiKeyAuthHandler(AuthHandler):
    """API Key authentication handler."""

    def __init__(self, auth_config: AuthConfig):
        super().__init__(auth_config)
        if not auth_config.api_key:
            raise ValueError('API Key auth requires an api_key')

    def generate_auth_headers(self, context: PipelineContext) -> Dict[str, str]:
        """Generate API Key headers."""
        return {self.auth_config.api_key_header: self.auth_config.api_key}


class AuthHandlerFactory:
    """Factory for creating authentication handlers."""

    @staticmethod
    def create_handler(auth_config: AuthConfig) -> AuthHandler:
        """Create appropriate auth handler based on auth type."""

        if auth_config.type == AuthType.BEARER:
            return BearerAuthHandler(auth_config)
        elif auth_config.type == AuthType.BASIC:
            return BasicAuthHandler(auth_config)
        elif auth_config.type == AuthType.API_KEY:
            return ApiKeyAuthHandler(auth_config)
        else:
            raise ValueError(f'Unsupported auth type: {auth_config.type}')
