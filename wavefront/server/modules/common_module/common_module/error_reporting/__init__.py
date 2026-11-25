"""Sentry error reporting, shared by the Python services.

Errors only: OpenTelemetry stays the only tracer, and each Sentry event is
linked to the active OTel trace id. This is the only package allowed to import
``sentry_sdk``; services call ``configure_error_reporting`` with their
settings and never touch the SDK directly.
"""

from .bootstrap import configure_error_reporting
from .bootstrap import error_reporting_enabled
from .bootstrap import shutdown_error_reporting
from .settings import ErrorReportingSettings

__all__ = [
    'configure_error_reporting',
    'error_reporting_enabled',
    'ErrorReportingSettings',
    'shutdown_error_reporting',
]
