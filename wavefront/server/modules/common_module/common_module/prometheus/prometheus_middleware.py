import time
from typing import Callable, Optional

from fastapi import Request
from fastapi import Response
from prometheus_client import Counter
from prometheus_client import Gauge
from prometheus_client import Histogram
from prometheus_client import REGISTRY
from prometheus_client.openmetrics.exposition import generate_latest
from starlette.middleware.base import BaseHTTPMiddleware


class PrometheusMiddleware(BaseHTTPMiddleware):
    _instance: Optional['PrometheusMiddleware'] = None

    def __init__(self, app):
        super().__init__(app)
        PrometheusMiddleware._instance = self

        # Common labels that will be used across all metrics
        self.common_labels = ['module', 'instance']

        # HTTP metrics
        self.http_requests_total = Counter(
            'http_requests_total',
            'Total number of HTTP requests',
            self.common_labels + ['method', 'endpoint', 'status_code'],
        )

        self.http_request_duration = Histogram(
            'http_request_duration_seconds',
            'HTTP request duration in seconds',
            self.common_labels + ['method', 'endpoint'],
        )

        self.http_requests_in_progress = Gauge(
            'http_requests_in_progress',
            'Number of HTTP requests in progress',
            self.common_labels + ['method', 'endpoint'],
        )

        self.http_errors_total = Counter(
            'http_errors_total',
            'Total number of HTTP errors',
            self.common_labels + ['method', 'endpoint', 'status_code'],
        )

    @classmethod
    def get_instance(cls) -> Optional['PrometheusMiddleware']:
        """Get the singleton instance of PrometheusMiddleware"""
        return cls._instance

    def get_labels(self, request: Request) -> dict:
        """Extract common labels from request"""
        return {
            'module': request.url.path.split('/')[3]
            if len(request.url.path.split('/')) > 3
            else 'root',
            'instance': f'{request.client.host}:{request.url.port}'
            if request.client
            else 'unknown:unknown',
            'method': request.method,
            'endpoint': request.url.path,
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip metrics endpoint to avoid infinite recursion
        if request.url.path == '/v1/_metrics':
            return await call_next(request)

        # Get common labels
        labels = self.get_labels(request)

        # Record request start
        self.http_requests_in_progress.labels(**labels).inc()

        # Start timing
        start_time = time.time()

        try:
            # Process the request
            response = await call_next(request)

            # Track errors for 4xx and 5xx status codes - ADD THIS
            if response and response.status_code >= 400:
                self.http_errors_total.labels(
                    **labels, status_code=response.status_code
                ).inc()

            # Record request duration
            duration = time.time() - start_time
            self.http_request_duration.labels(**labels).observe(duration)

            # Record request completion
            self.http_requests_total.labels(
                **labels, status_code=response.status_code
            ).inc()

            return response

        except Exception as e:
            # Record error
            self.http_requests_total.labels(
                **labels, status_code=getattr(e, 'status_code', 500)
            ).inc()

            self.http_errors_total.labels(
                **labels, status_code=getattr(e, 'status_code', 500)
            ).inc()

            raise
        finally:
            # Decrement in-progress counter
            self.http_requests_in_progress.labels(**labels).dec()

    @staticmethod
    async def metrics_endpoint(request: Request) -> Response:
        """Endpoint to expose Prometheus metrics"""
        return Response(content=generate_latest(REGISTRY), media_type='text/plain')
