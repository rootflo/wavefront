"""Pluggable authentication and authorization for wavefront services."""

from authz_module.actions import ActionSpec, all_actions, define_action, get_action
from authz_module.context import RequestContext, current_principal
from authz_module.dependencies import (
    RouteAuthz,
    current_principal_dependency,
    decide,
    ensure_allowed,
    is_allowed,
    principal_of,
    public_route,
    requires,
)
from authz_module.legacy import Legacy, LegacyRule
from authz_module.loader import load_provider
from authz_module.principal import (
    ANONYMOUS,
    Principal,
    PrincipalType,
    service_principal,
    user_principal,
)
from authz_module.protocols import (
    AccessDenied,
    AuthenticationError,
    Authenticator,
    Authorizer,
    BaseAuthorizer,
    Capability,
    DataQuery,
    Decision,
    DecisionEvent,
)
from authz_module.provider import AuthzProvider, install
from authz_module.resource import ResourceRef, from_path

__version__ = '0.1.0'

__all__ = [
    'ANONYMOUS',
    'AccessDenied',
    'ActionSpec',
    'AuthenticationError',
    'Authenticator',
    'Authorizer',
    'AuthzProvider',
    'BaseAuthorizer',
    'Capability',
    'DataQuery',
    'Decision',
    'DecisionEvent',
    'Legacy',
    'LegacyRule',
    'Principal',
    'PrincipalType',
    'RequestContext',
    'ResourceRef',
    'RouteAuthz',
    'all_actions',
    'current_principal',
    'current_principal_dependency',
    'decide',
    'define_action',
    'ensure_allowed',
    'from_path',
    'get_action',
    'install',
    'is_allowed',
    'load_provider',
    'principal_of',
    'public_route',
    'requires',
    'service_principal',
    'user_principal',
]
