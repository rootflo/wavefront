"""SecurityHeadersMiddleware takes its environment as an argument."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from common_module.middleware.security_headers import SecurityHeadersMiddleware


def _client(environment: str) -> TestClient:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, environment=environment)

    @app.get('/docs-like')
    def ping():
        return {'ok': True}

    return TestClient(app)


def test_docs_are_only_relaxed_in_dev():
    assert SecurityHeadersMiddleware(app=None, environment='dev').docs_enabled is True
    assert (
        SecurityHeadersMiddleware(app=None, environment='production').docs_enabled
        is False
    )


def test_unknown_environment_stays_closed():
    assert (
        SecurityHeadersMiddleware(app=None, environment='staging').docs_enabled is False
    )


def test_headers_are_added_to_api_responses():
    response = _client('production').get('/docs-like')

    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['X-Frame-Options'] == 'DENY'
