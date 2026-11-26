"""
Test configuration for common module tests.
Sets up mock FastAPI app with middleware for testing.
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

# Import your middleware
from common_module.middleware.request_id_middleware import RequestIdMiddleware


@pytest.fixture
def mock_app():
    """Create a minimal FastAPI app with RequestIdMiddleware for testing."""
    app = FastAPI(title='Test App')

    # Add your middleware
    app.add_middleware(RequestIdMiddleware)

    # Add test endpoints
    @app.get('/test')
    async def test_endpoint(request: Request):
        """Test endpoint that returns request info."""
        request_id = getattr(request.state, 'request_id', 'NOT_FOUND')
        return {
            'message': 'Test successful',
            'request_id_in_state': request_id,
        }

    @app.get('/metrics')
    async def metrics_endpoint():
        """Mock metrics endpoint used to exercise middleware on a plain route."""
        return {'metrics': 'mock_data'}

    @app.get('/error')
    async def error_endpoint():
        """Endpoint that raises an error for testing error handling."""
        raise Exception('Test error')

    return app


@pytest.fixture
def client(mock_app):
    """Create TestClient with the mock app."""
    return TestClient(mock_app)


@pytest.fixture
def mock_request():
    """Create a mock request object for unit testing."""
    from unittest.mock import Mock

    mock_req = Mock()
    mock_req.headers = {}
    mock_req.state = Mock()
    return mock_req


class _CapturingTransport:
    """Builds a sentry_sdk Transport that keeps events in memory."""

    @staticmethod
    def create():
        from sentry_sdk.transport import Transport

        class Capturing(Transport):
            def __init__(self):
                super().__init__()
                self.envelopes = []

            def capture_envelope(self, envelope):
                self.envelopes.append(envelope)

            @property
            def events(self):
                return [
                    item.payload.json
                    for envelope in self.envelopes
                    for item in envelope.items
                    if item.type == 'event'
                ]

        return Capturing()


@pytest.fixture
def start_sentry():
    """Start error reporting with an in-memory transport; reset afterwards.

    Returns a function: ``transport = start_sentry(frameworks=..., **settings)``.
    """
    from common_module.error_reporting import (
        ErrorReportingSettings,
        configure_error_reporting,
    )
    from common_module.error_reporting import bootstrap

    bootstrap._reset_for_tests()

    def start(frameworks=(), **overrides):
        transport = _CapturingTransport.create()
        settings = ErrorReportingSettings(
            service_name='test-service',
            dsn='https://public@example.invalid/1',
            **overrides,
        )
        assert configure_error_reporting(
            settings, frameworks=frameworks, _transport=transport
        )
        return transport

    yield start
    bootstrap._reset_for_tests()
