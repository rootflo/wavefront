"""
Floware API Services Module

Enterprise-grade API proxy middleware that acts as an intelligent gateway
between clients and multiple backend services. Handles routing, authentication
injection, and request/response transformation through declarative YAML configuration.
"""

from .core.proxy import ApiProxy
from .core.router import ProxyRouter
from .config.registry import ServiceRegistry
from .config.parser import ServiceDefinitionParser
from .auth.manager import AuthManager
from .models.service import ServiceDefinition, AuthConfig, ApiConfig, ProxyResponse
from .models.pipeline import PipelineContext, PipelineStage, CompositePipelineStage
from .api_services_container import ApiServicesContainer, create_api_services_container
from .execution.execute import execute_api_service

__version__ = '1.0.0'
__author__ = 'Floware Team'

__all__ = [
    # Core components
    'ApiProxy',
    'ProxyRouter',
    # Configuration
    'ServiceRegistry',
    'ServiceDefinitionParser',
    # Authentication
    'AuthManager',
    # Models
    'ServiceDefinition',
    'AuthConfig',
    'ApiConfig',
    'ProxyResponse',
    'PipelineContext',
    'PipelineStage',
    'CompositePipelineStage',
    # Dependency Injection
    'ApiServicesContainer',
    'create_api_services_container',
    # Utility Functions
    'execute_api_service',
]
