"""PostgreSQL fixtures built on one cluster per session and a template clone per test.

The schema is expensive to stand up and identical for every test, so it is built
exactly once into a template database. Each test then gets a private database
via ``CREATE DATABASE ... TEMPLATE``, which Postgres serves as a file copy of an
already-initialised directory. Measured on this schema: ~1.4s to boot the
cluster plus ~0.3s to create 57 tables, once, against ~0.14s per test to clone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine

if TYPE_CHECKING:
    from sqlalchemy.engine import URL

TEMPLATE_DATABASE = 'wf_template'

_SYNC_DRIVER = 'postgresql+psycopg'
_ASYNC_DRIVER = 'postgresql+psycopg'


class StubDbClient:
    """Stands in for ``db_repo_module``'s ``DatabaseClient``.

    The repositories only ever touch ``.session``, so this exposes that plus the
    engine and skips the real client's connection pooling and config plumbing.
    """

    def __init__(self, engine, session_factory):
        self._engine = engine
        self.session = session_factory


def _database_url(url: URL, name: str, driver: str = _SYNC_DRIVER) -> URL:
    return make_url(str(url)).set(drivername=driver, database=name)


def _run_admin_statements(url: URL, *statements: str) -> None:
    """Run statements that cannot sit inside a transaction (CREATE/DROP DATABASE)."""
    engine = sa.create_engine(
        _database_url(url, url.database or 'postgres'),
        isolation_level='AUTOCOMMIT',
    )
    try:
        with engine.connect() as conn:
            for statement in statements:
                conn.exec_driver_sql(statement)
    finally:
        engine.dispose()


@pytest.fixture(scope='session')
def postgres_cluster():
    """One throwaway PostgreSQL cluster for the whole session.

    Under xdist each worker is its own pytest session and so gets its own
    cluster on its own port, which keeps workers from sharing state.
    """
    import testing.postgresql

    with testing.postgresql.Postgresql() as cluster:
        yield cluster


@pytest.fixture(scope='session')
def postgres_template(postgres_cluster) -> URL:
    """Build the full schema once into a template database.

    Returns the cluster URL; callers clone ``TEMPLATE_DATABASE`` off it.
    """
    # Importing the package registers every model on Base.metadata. Without it
    # create_all trips over the first unresolved cross-module foreign key.
    import db_repo_module.models  # noqa: F401
    from db_repo_module.database.base import Base

    cluster_url = make_url(postgres_cluster.url())

    _run_admin_statements(
        cluster_url,
        f'DROP DATABASE IF EXISTS {TEMPLATE_DATABASE}',
        f'CREATE DATABASE {TEMPLATE_DATABASE}',
    )

    engine = sa.create_engine(_database_url(cluster_url, TEMPLATE_DATABASE))
    try:
        with engine.begin() as conn:
            Base.metadata.create_all(conn)
    finally:
        engine.dispose()

    return cluster_url


@pytest.fixture
async def test_engine(postgres_template):
    """An async engine bound to a private, schema-ready database for this test."""
    cluster_url = postgres_template
    name = f'test_{uuid4().hex}'

    _run_admin_statements(
        cluster_url,
        f'CREATE DATABASE {name} TEMPLATE {TEMPLATE_DATABASE}',
    )

    engine = create_async_engine(_database_url(cluster_url, name, _ASYNC_DRIVER))
    try:
        yield engine
    finally:
        await engine.dispose()
        # Dropping keeps the cluster's disk footprint flat over a long session.
        # Connections are already gone, so this needs no FORCE.
        _run_admin_statements(cluster_url, f'DROP DATABASE IF EXISTS {name}')


@pytest.fixture
async def test_session(test_engine) -> async_sessionmaker:
    """Session factory bound to this test's database.

    Yields the factory rather than a session because the repositories open their
    own sessions; tests use it directly for seeding and assertions.
    """
    return async_sessionmaker(autocommit=False, bind=test_engine)


@pytest.fixture
def db_client(test_engine, test_session) -> StubDbClient:
    return StubDbClient(test_engine, test_session)
