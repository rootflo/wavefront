"""Floware's Sentry wiring: config section, start-up helper, middleware order.

Files are loaded directly: importing the floware.di package builds the DI
container, which needs the full deployment environment.
"""

from __future__ import annotations

import configparser
import importlib.util
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from common_module.config_loader import _resolve_env_markers
from common_module.error_reporting import (
    ErrorReportingContextMiddleware,
    ErrorReportingSettings,
)
from common_module.middleware.request_id_middleware import RequestIdMiddleware
from common_module.telemetry import BaggageMiddleware
from user_management_module.authorization.require_auth import RequireAuthMiddleware

FLOWARE = Path(__file__).resolve().parents[1] / 'floware'
SENTRY_VARS = (
    'SENTRY_DSN',
    'SENTRY_ENVIRONMENT',
    'SENTRY_RELEASE',
    'SENTRY_SAMPLE_RATE',
    'SENTRY_BREADCRUMB_LEVEL',
    'SENTRY_LOOP_BLOCKS',
)


def _load(relative: str, name: str):
    spec = importlib.util.spec_from_file_location(name, FLOWARE / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sentry_section() -> dict[str, str]:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(FLOWARE / 'config.ini')
    return {key: _resolve_env_markers(value) for key, value in parser.items('sentry')}


def test_sentry_is_off_without_environment(monkeypatch):
    for name in SENTRY_VARS:
        monkeypatch.delenv(name, raising=False)

    settings = ErrorReportingSettings.from_config(
        {'env_config': {'app_env': 'dev'}, 'sentry': _sentry_section()},
        default_service_name='floware',
    )

    assert settings.dsn is None
    assert settings.environment == 'dev'
    assert settings.release is None
    assert settings.sample_rate == 1.0
    assert settings.breadcrumb_level == logging.WARNING
    assert settings.report_loop_blocks is True


def test_sentry_reads_its_environment(monkeypatch):
    monkeypatch.setenv('SENTRY_DSN', 'https://public@example.invalid/1')
    monkeypatch.setenv('SENTRY_ENVIRONMENT', 'tenant-dev')
    monkeypatch.setenv('SENTRY_RELEASE', 'abc123')
    monkeypatch.setenv('SENTRY_LOOP_BLOCKS', 'false')

    settings = ErrorReportingSettings.from_config(
        {'env_config': {'app_env': 'dev'}, 'sentry': _sentry_section()},
        default_service_name='floware',
    )

    assert settings.dsn == 'https://public@example.invalid/1'
    assert settings.environment == 'tenant-dev'
    assert settings.release == 'abc123'
    assert settings.report_loop_blocks is False


def test_start_error_reporting_configures_fastapi(monkeypatch):
    helpers = _load('di/helpers.py', 'floware_helpers_under_test')
    calls = []
    monkeypatch.setattr(
        'common_module.error_reporting.configure_error_reporting',
        lambda settings, frameworks: calls.append((settings, frameworks)),
    )

    helpers.start_error_reporting(
        {
            'env_config': {'app_name': 'floware', 'app_env': 'qa'},
            'sentry': {'dsn': 'https://public@example.invalid/1'},
        }
    )

    ((settings, frameworks),) = calls
    assert frameworks == ('fastapi',)
    assert settings.service_name == 'floware'
    assert settings.environment == 'qa'


def test_container_starts_error_reporting_after_telemetry():
    source = (FLOWARE / 'di' / 'application_container.py').read_text()
    telemetry = source.index('telemetry = providers.Resource(start_telemetry')
    error_reporting = source.index(
        'error_reporting = providers.Resource(start_error_reporting'
    )
    assert telemetry < error_reporting


@pytest.fixture
def middleware_order(monkeypatch):
    setup = _load('middleware/setup.py', 'floware_middleware_setup_under_test')
    monkeypatch.setattr(setup, 'instrument_fastapi', lambda app: None)
    app = FastAPI()
    runtime = SimpleNamespace(
        app_env='dev', passthrough_secret=None, allowed_origins=('http://x',)
    )
    setup.add_middlewares(
        app, runtime=runtime, hmac_routes=(), mtls_allowed_namespaces=()
    )
    # app.user_middleware is outermost first.
    return [middleware.cls for middleware in app.user_middleware]


def test_context_middleware_runs_inside_auth_and_request_id(middleware_order):
    position = middleware_order.index
    assert position(RequireAuthMiddleware) < position(ErrorReportingContextMiddleware)
    assert position(RequestIdMiddleware) < position(ErrorReportingContextMiddleware)
    assert position(ErrorReportingContextMiddleware) < position(BaggageMiddleware)
