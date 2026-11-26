"""Sentry error reporting, shared by the Python services.

Errors only: OpenTelemetry stays the only tracer, and each Sentry event is
linked to the active OTel trace id. This is the only package allowed to import
``sentry_sdk``; services call ``configure_error_reporting`` with their
settings and never touch the SDK directly.
"""

from .bootstrap import configure_error_reporting
from .bootstrap import error_reporting_enabled
from .bootstrap import shutdown_error_reporting
from .context import ErrorReportingContextMiddleware
from .loop_blocks import start_loop_block_reporting
from .loop_blocks import stop_loop_block_reporting
from .settings import ErrorReportingSettings

__all__ = [
    'configure_error_reporting',
    'error_reporting_enabled',
    'ErrorReportingContextMiddleware',
    'ErrorReportingSettings',
    'shutdown_error_reporting',
    'start_loop_block_reporting',
    'stop_loop_block_reporting',
]
