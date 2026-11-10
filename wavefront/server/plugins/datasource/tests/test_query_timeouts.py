"""
Tests for the connect and statement timeouts on datasource SQL clients
"""

from unittest.mock import patch

import mssql_python
import pytest
from datasource.executor import (
    DATASOURCE_CONNECT_TIMEOUT_SECONDS,
    DATASOURCE_STATEMENT_TIMEOUT_SECONDS,
    SCHEDULED_STATEMENT_TIMEOUT_SECONDS,
    statement_timeout_limit,
)
from datasource.mssql import MSSQLConfig, MSSQLPlugin
from datasource.postgres import PostgresConfig, PostgresPlugin
from datasource.redshift import RedshiftConfig, RedshiftPlugin
from flo_cloud.mssql import MSSQLClient
from flo_cloud.postgres import PostgresClient


def _executed_sql(connect):
    cursor = connect.return_value.cursor.return_value.__enter__.return_value
    return [c.args for c in cursor.execute.call_args_list]


def test_postgres_plugin_bounds_connect_and_statement_time():
    plugin = PostgresPlugin(PostgresConfig('h', 5432, 'db', 'u', 'p'))

    assert plugin.client.timeout == DATASOURCE_CONNECT_TIMEOUT_SECONDS
    assert plugin.client.statement_timeout == DATASOURCE_STATEMENT_TIMEOUT_SECONDS


@patch('flo_cloud.postgres.postgres.psycopg2.connect')
def test_statement_timeout_is_set_in_milliseconds_before_search_path(connect):
    client = PostgresClient('h', database='db', schema='tenant', statement_timeout=30)

    with client.get_connection():
        pass

    executed = _executed_sql(connect)
    assert executed[0] == ('SET statement_timeout = %s', (30000,))
    assert len(executed) == 2  # then SET search_path


@patch('flo_cloud.postgres.postgres.psycopg2.connect')
def test_statement_timeout_applies_without_a_schema(connect):
    client = PostgresClient('h', database='db', schema=None, statement_timeout=5)

    with client.get_connection():
        pass

    assert _executed_sql(connect) == [('SET statement_timeout = %s', (5000,))]


@patch('flo_cloud.postgres.postgres.psycopg2.connect')
def test_no_statement_timeout_leaves_the_server_setting(connect):
    client = PostgresClient('h', database='db', schema=None)

    with client.get_connection():
        pass

    assert _executed_sql(connect) == []


def test_mssql_plugin_bounds_login_and_statement_time():
    plugin = MSSQLPlugin(MSSQLConfig('h', 1433, 'db', 'u', 'p'))

    assert plugin.client.timeout == DATASOURCE_CONNECT_TIMEOUT_SECONDS
    assert plugin.client.statement_timeout == DATASOURCE_STATEMENT_TIMEOUT_SECONDS


@patch('flo_cloud.mssql.mssql.mssql_python.connect')
def test_mssql_passes_login_and_query_timeouts_to_the_driver(connect):
    client = MSSQLClient('h', database='db', timeout=10, statement_timeout=30)

    with client.get_connection():
        pass

    kwargs = connect.call_args.kwargs
    assert kwargs['attrs_before'] == {mssql_python.SQL_ATTR_LOGIN_TIMEOUT: 10}
    assert kwargs['timeout'] == 30


def test_postgres_connections_use_tcp_keepalives():
    params = PostgresClient('h', database='db')._get_connection_params()

    assert params['keepalives'] == 1
    assert params['keepalives_idle'] == 30
    assert params['keepalives_interval'] == 10
    assert params['keepalives_count'] == 3


@pytest.mark.parametrize(
    'plugin_class, config',
    [
        (PostgresPlugin, PostgresConfig('h', 5432, 'db', 'u', 'p')),
        (MSSQLPlugin, MSSQLConfig('h', 1433, 'db', 'u', 'p')),
        (RedshiftPlugin, RedshiftConfig('h', 5439, 'db', 'u', 'p')),
    ],
    ids=['postgres', 'mssql', 'redshift'],
)
def test_scheduled_context_gets_the_long_statement_limit(plugin_class, config):
    token = statement_timeout_limit.set(SCHEDULED_STATEMENT_TIMEOUT_SECONDS)
    try:
        plugin = plugin_class(config)
    finally:
        statement_timeout_limit.reset(token)

    assert plugin.client.statement_timeout == SCHEDULED_STATEMENT_TIMEOUT_SECONDS
    # Clients built outside that context keep the request limit.
    assert (
        plugin_class(config).client.statement_timeout
        == DATASOURCE_STATEMENT_TIMEOUT_SECONDS
    )
