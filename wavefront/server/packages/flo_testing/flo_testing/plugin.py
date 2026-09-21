"""pytest plugin entry point for the shared harness.

Loaded automatically for any pytest run in this workspace, via the ``pytest11``
entry point in ``pyproject.toml``. Every fixture here is lazy, so suites that
never ask for a database never start one.
"""

from __future__ import annotations

import os

# Both of these are read at import time -- APP_ENV decides whether the embedding
# columns map to pgvector's Vector or to Text (tests use Text so the cluster
# needs no extension), and SUPERSET_FLAG decides whether AuthContainer even
# defines superset_service. They therefore have to be set before any module
# import, which is earlier than any fixture or hook can run; plugin import is
# the first point available. setdefault, so an explicit value still wins.
os.environ.setdefault('APP_ENV', 'test')
os.environ.setdefault('SUPERSET_FLAG', 'true')

from flo_testing.app import build_app  # noqa: E402
from flo_testing.app import make_test_client  # noqa: E402
from flo_testing.auth import patch_auth  # noqa: E402,F401
from flo_testing.auth import patch_current_user  # noqa: E402,F401
from flo_testing.auth import patch_feature_flag  # noqa: E402,F401
from flo_testing.auth import patch_is_admin  # noqa: E402,F401
from flo_testing.containers import CoreContainers  # noqa: E402
from flo_testing.containers import core_containers  # noqa: E402,F401
from flo_testing.containers import user_config  # noqa: E402,F401
from flo_testing.db import StubDbClient  # noqa: E402
from flo_testing.db import db_client  # noqa: E402,F401
from flo_testing.db import postgres_cluster  # noqa: E402,F401
from flo_testing.db import postgres_template  # noqa: E402,F401
from flo_testing.db import test_engine  # noqa: E402,F401
from flo_testing.db import test_session  # noqa: E402,F401
from flo_testing.factories import seed_session  # noqa: E402,F401
from flo_testing.factories import seed_user_session  # noqa: E402
from flo_testing.identity import auth_headers  # noqa: E402,F401
from flo_testing.identity import auth_token  # noqa: E402,F401
from flo_testing.identity import test_session_id  # noqa: E402,F401
from flo_testing.identity import test_user_id  # noqa: E402,F401

__all__ = [
    'CoreContainers',
    'StubDbClient',
    'build_app',
    'make_test_client',
    'seed_user_session',
]


def pytest_configure(config):
    config.addinivalue_line('markers', 'db: test needs a PostgreSQL database')
