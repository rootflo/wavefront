"""pytest plugin entry point for the shared harness.

Loaded automatically for any pytest run in this workspace, via the ``pytest11``
entry point in ``pyproject.toml``. Every fixture here is lazy, so suites that
never ask for a database never start one.
"""

from __future__ import annotations

from flo_lib.http import alias_httpx

alias_httpx()

# ruff: noqa: E402
from db_repo_module.embedding_column_mode import enable_pgvector_test_standins

# Before any ``db_repo_module.models`` import: Text stand-ins instead of pgvector.
enable_pgvector_test_standins()

# ruff: noqa: E402
from flo_testing.app import build_app
from flo_testing.app import make_test_client
from flo_testing.auth import patch_auth  # noqa: F401
from flo_testing.auth import patch_current_user  # noqa: F401
from flo_testing.auth import patch_feature_flag  # noqa: F401
from flo_testing.auth import patch_is_admin  # noqa: F401
from flo_testing.containers import CoreContainers
from flo_testing.containers import core_containers  # noqa: F401
from flo_testing.containers import user_config  # noqa: F401
from flo_testing.db import StubDbClient
from flo_testing.db import db_client  # noqa: F401
from flo_testing.db import postgres_cluster  # noqa: F401
from flo_testing.db import postgres_template  # noqa: F401
from flo_testing.db import test_engine  # noqa: F401
from flo_testing.db import test_session  # noqa: F401
from flo_testing.factories import seed_session  # noqa: F401
from flo_testing.factories import seed_user_session
from flo_testing.identity import auth_headers  # noqa: F401
from flo_testing.identity import auth_token  # noqa: F401
from flo_testing.identity import test_session_id  # noqa: F401
from flo_testing.identity import test_user_id  # noqa: F401

__all__ = [
    'CoreContainers',
    'StubDbClient',
    'build_app',
    'make_test_client',
    'seed_user_session',
]


def pytest_configure(config):
    config.addinivalue_line('markers', 'db: test needs a PostgreSQL database')
