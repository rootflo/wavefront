"""
OpenTelemetry telemetry implementation for flo_ai framework
"""

from typing import Optional, Dict, Any
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    PeriodicExportingMetricReader,
    ConsoleMetricExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
import os


class FloTelemetry:
    """
    Central telemetry configuration for flo_ai framework.

    Provides OpenTelemetry integration with tracing and metrics support.
    """

    _instance: Optional['FloTelemetry'] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FloTelemetry, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not FloTelemetry._initialized:
            self.tracer_provider: Optional[TracerProvider] = None
            self.meter_provider: Optional[MeterProvider] = None
            self.tracer: Optional[trace.Tracer] = None
            self.meter: Optional[metrics.Meter] = None
            FloTelemetry._initialized = True

    def configure(
        self,
        service_name: str = 'flo_ai',
        service_version: str = '1.0.0',
        environment: str = 'development',
        otlp_endpoint: Optional[str] = None,
        console_export: bool = False,
        additional_attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Configure OpenTelemetry for the flo_ai framework.

        Args:
            service_name: Name of the service for telemetry
            service_version: Version of the service
            environment: Environment (development, production, etc.)
            otlp_endpoint: OTLP endpoint for exporting telemetry (e.g., http://localhost:4317)
            console_export: Whether to export to console for debugging
            additional_attributes: Additional resource attributes
        """
        # Create resource with service information
        resource_attrs = {
            'service.name': service_name,
            'service.version': service_version,
            'deployment.environment': environment,
        }

        if additional_attributes:
            resource_attrs.update(additional_attributes)

        resource = Resource.create(resource_attrs)

        # Configure tracing
        self.tracer_provider = TracerProvider(resource=resource)

        # Add span processors
        if console_export:
            console_processor = BatchSpanProcessor(ConsoleSpanExporter())
            self.tracer_provider.add_span_processor(console_processor)

        # Add OTLP exporter if endpoint is provided
        if otlp_endpoint:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            otlp_processor = BatchSpanProcessor(otlp_exporter)
            self.tracer_provider.add_span_processor(otlp_processor)

        # Set the tracer provider
        trace.set_tracer_provider(self.tracer_provider)
        self.tracer = trace.get_tracer(__name__)

        # Configure metrics
        metric_readers = []

        if console_export:
            console_reader = PeriodicExportingMetricReader(
                ConsoleMetricExporter(), export_interval_millis=5000
            )
            metric_readers.append(console_reader)

        if otlp_endpoint:
            otlp_metric_exporter = OTLPMetricExporter(
                endpoint=otlp_endpoint, insecure=True
            )
            otlp_reader = PeriodicExportingMetricReader(
                otlp_metric_exporter, export_interval_millis=5000
            )
            metric_readers.append(otlp_reader)

        if metric_readers:
            self.meter_provider = MeterProvider(
                resource=resource,
                metric_readers=metric_readers,
            )
            metrics.set_meter_provider(self.meter_provider)
            self.meter = metrics.get_meter(__name__)

    def get_tracer(self) -> Optional[trace.Tracer]:
        """Get the configured tracer instance"""
        return self.tracer

    def get_meter(self) -> Optional[metrics.Meter]:
        """Get the configured meter instance"""
        return self.meter

    def shutdown(self) -> None:
        """Shutdown telemetry providers and flush data"""
        if self.tracer_provider:
            self.tracer_provider.shutdown()
        if self.meter_provider:
            self.meter_provider.shutdown()


# Global telemetry instance
_global_telemetry = FloTelemetry()


def configure_telemetry(
    service_name: str = 'flo_ai',
    service_version: str = '1.0.0',
    environment: str = None,
    otlp_endpoint: str = None,
    console_export: bool = False,
    additional_attributes: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Configure OpenTelemetry for flo_ai.

    Args:
        service_name: Name of the service
        service_version: Version of the service
        environment: Environment (defaults to FLO_ENV or 'development')
        otlp_endpoint: OTLP endpoint (defaults to FLO_OTLP_ENDPOINT or None)
        console_export: Export to console for debugging
        additional_attributes: Additional resource attributes

    Example:
        >>> from flo_ai.telemetry import configure_telemetry
        >>> configure_telemetry(
        ...     service_name="my_ai_app",
        ...     otlp_endpoint="http://localhost:4317",
        ...     console_export=True
        ... )
    """
    # Use environment variables as defaults
    if environment is None:
        environment = os.getenv('FLO_ENV', 'development')

    if otlp_endpoint is None:
        otlp_endpoint = os.getenv('FLO_OTLP_ENDPOINT')

    _global_telemetry.configure(
        service_name=service_name,
        service_version=service_version,
        environment=environment,
        otlp_endpoint=otlp_endpoint,
        console_export=console_export,
        additional_attributes=additional_attributes,
    )


def get_tracer() -> Optional[trace.Tracer]:
    """
    Get the global tracer instance.

    Returns:
        Tracer instance or None if not configured

    Example:
        >>> from flo_ai.telemetry import get_tracer
        >>> tracer = get_tracer()
        >>> if tracer:
        ...     with tracer.start_as_current_span("my_operation"):
        ...         # Your code here
        ...         pass
    """
    return _global_telemetry.get_tracer()


def get_meter() -> Optional[metrics.Meter]:
    """
    Get the global meter instance.

    Returns:
        Meter instance or None if not configured

    Example:
        >>> from flo_ai.telemetry import get_meter
        >>> meter = get_meter()
        >>> if meter:
        ...     counter = meter.create_counter("operations_total")
        ...     counter.add(1, {"operation": "inference"})
    """
    return _global_telemetry.get_meter()


def shutdown_telemetry() -> None:
    """
    Shutdown telemetry and flush all data.

    Call this at the end of your application lifecycle.

    Example:
        >>> from flo_ai.telemetry import shutdown_telemetry
        >>> shutdown_telemetry()
    """
    _global_telemetry.shutdown()
