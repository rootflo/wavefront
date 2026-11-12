"""
Tests for the connect and statement timeouts on datasource SQL clients
"""

from unittest.mock import MagicMock, patch

import contextvars

import mssql_python
import psycopg2
import pytest
from datasource.executor import (
    DATASOURCE_CONNECT_TIMEOUT_SECONDS,
    DATASOURCE_SCHEDULED_STATEMENT_TIMEOUT_SECONDS,
    DATASOURCE_STATEMENT_TIMEOUT_SECONDS,
    use_scheduled_limits,
)
from datasource.bigquery import BigQueryConfig, BigQueryPlugin
from datasource.mssql import MSSQLConfig, MSSQLPlugin
from datasource.postgres import PostgresConfig, PostgresPlugin
from datasource.redshift import RedshiftConfig, RedshiftPlugin
from flo_cloud.aws.redshift import RedshiftClient
from flo_cloud.gcp.bigquery import BigQueryClient
from flo_cloud.mssql import MSSQLClient
from flo_cloud.postgres import PostgresClient
from flo_cloud.postgres.postgres import _duration_setting_ms

SHOW = ('SHOW statement_timeout',)


def _cursor(connect, server_setting='0'):
    cursor = connect.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (server_setting,)
    return cursor


def _executed_sql(cursor):
    return [c.args for c in cursor.execute.call_args_list]


def test_postgres_plugin_bounds_connect_and_statement_time():
    plugin = PostgresPlugin(PostgresConfig('h', 5432, 'db', 'u', 'p'))

    assert plugin.client.timeout == DATASOURCE_CONNECT_TIMEOUT_SECONDS
    assert plugin.client.statement_timeout == DATASOURCE_STATEMENT_TIMEOUT_SECONDS


@patch('flo_cloud.postgres.postgres.psycopg2.connect')
def test_statement_timeout_is_set_in_milliseconds_before_search_path(connect):
    cursor = _cursor(connect)
    client = PostgresClient('h', database='db', schema='tenant', statement_timeout=30)

    with client.get_connection():
        pass

    executed = _executed_sql(cursor)
    assert executed[:2] == [SHOW, ('SET statement_timeout = %s', (30000,))]
    assert len(executed) == 3  # then SET search_path


@patch('flo_cloud.postgres.postgres.psycopg2.connect')
def test_statement_timeout_applies_without_a_schema(connect):
    cursor = _cursor(connect)
    client = PostgresClient('h', database='db', schema=None, statement_timeout=5)

    with client.get_connection():
        pass

    assert _executed_sql(cursor) == [SHOW, ('SET statement_timeout = %s', (5000,))]


@pytest.mark.parametrize('server_setting', ['5s', '30s', '1000ms', '20000'])
@patch('flo_cloud.postgres.postgres.psycopg2.connect')
def test_stricter_server_limit_is_kept(connect, server_setting):
    cursor = _cursor(connect, server_setting)
    client = PostgresClient('h', database='db', schema=None, statement_timeout=30)

    with client.get_connection():
        pass

    assert _executed_sql(cursor) == [SHOW]


@pytest.mark.parametrize('server_setting', ['0', '1min', '45s', 'not-a-duration'])
@patch('flo_cloud.postgres.postgres.psycopg2.connect')
def test_looser_or_unreadable_server_limit_is_replaced(connect, server_setting):
    cursor = _cursor(connect, server_setting)
    client = PostgresClient('h', database='db', schema=None, statement_timeout=30)

    with client.get_connection():
        pass

    assert _executed_sql(cursor) == [SHOW, ('SET statement_timeout = %s', (30000,))]


@pytest.mark.parametrize(
    'value, expected',
    [
        ('0', 0),
        ('250', 250),
        ('250ms', 250),
        ('5s', 5000),
        ('2min', 120000),
        ('1h', 3600000),
        ('1d', 86400000),
        ('5 s', 5000),
        ('', None),
        ('1.5s', None),
    ],
)
def test_duration_setting_parsing(value, expected):
    assert _duration_setting_ms(value) == expected


@patch('flo_cloud.postgres.postgres.psycopg2.connect')
def test_no_statement_timeout_leaves_the_server_setting(connect):
    cursor = _cursor(connect)
    client = PostgresClient('h', database='db', schema=None)

    with client.get_connection():
        pass

    assert _executed_sql(cursor) == []


@patch('flo_cloud.aws.redshift.redshift_connector.connect')
def test_redshift_connects_with_the_short_limit_then_reads_past_the_statement(connect):
    client = RedshiftClient(
        host='h',
        database='db',
        user='u',
        password='p',
        timeout=30,
        statement_timeout=300,
    )

    with client.get_connection():
        pass

    assert connect.call_args.kwargs['timeout'] == 30
    connection = connect.return_value
    connection._usock.settimeout.assert_called_once_with(330)
    connection.cursor.return_value.execute.assert_called_once_with(
        'SET statement_timeout TO 300000'
    )


@patch('flo_cloud.aws.redshift.redshift_connector.connect')
def test_redshift_without_a_statement_limit_is_left_alone(connect):
    client = RedshiftClient(host='h', database='db', user='u', password='p')

    with client.get_connection():
        pass

    connect.return_value._usock.settimeout.assert_not_called()
    connect.return_value.cursor.return_value.execute.assert_not_called()


@patch('flo_cloud.postgres.postgres.psycopg2.connect')
def test_postgres_that_rejects_the_setting_still_connects(connect):
    cursor = _cursor(connect)
    cursor.execute.side_effect = [psycopg2.Error('unsupported'), None]
    client = PostgresClient('h', database='db', schema='tenant', statement_timeout=30)

    with client.get_connection():
        pass

    connect.return_value.rollback.assert_called_once()
    assert len(_executed_sql(cursor)) == 2  # the failed SHOW, then search_path


def _bigquery_client(timeout):
    client = object.__new__(BigQueryClient)
    client.timeout = timeout
    client.client = MagicMock()
    return client


def test_bigquery_query_is_bounded_on_server_and_client():
    client = _bigquery_client(30)
    job = client.client.query.return_value
    job.result.return_value = [MagicMock(items=lambda: [('id', 1)])]

    rows = client.query_rows('SELECT 1')

    assert rows == [{'id': 1}]
    job_config = client.client.query.call_args.kwargs['job_config']
    # The library keeps it in its API form, a string of milliseconds.
    assert int(job_config.job_timeout_ms) == 30000
    assert client.client.query.call_args.kwargs['timeout'] == 30
    job.result.assert_called_once_with(timeout=30)


def test_bigquery_query_over_the_limit_is_cancelled_with_a_clear_error():
    client = _bigquery_client(30)
    job = client.client.query.return_value
    job.result.side_effect = TimeoutError()

    with pytest.raises(TimeoutError, match='did not finish within 30s'):
        client.query_rows('SELECT 1')

    job.cancel.assert_called_once()


def test_bigquery_plugin_uses_the_context_limit():
    with patch('datasource.bigquery.BigQueryClient') as client_class:
        BigQueryPlugin(BigQueryConfig('p', 'd', 'US'))
        scheduled = contextvars.copy_context()
        scheduled.run(use_scheduled_limits)
        scheduled.run(BigQueryPlugin, BigQueryConfig('p', 'd', 'US'))

    timeouts = [c.kwargs['timeout'] for c in client_class.call_args_list]
    assert timeouts == [
        DATASOURCE_STATEMENT_TIMEOUT_SECONDS,
        DATASOURCE_SCHEDULED_STATEMENT_TIMEOUT_SECONDS,
    ]


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
    scheduled = contextvars.copy_context()
    scheduled.run(use_scheduled_limits)
    plugin = scheduled.run(plugin_class, config)

    assert (
        plugin.client.statement_timeout
        == DATASOURCE_SCHEDULED_STATEMENT_TIMEOUT_SECONDS
    )
    # Clients built outside that context keep the request limit.
    assert (
        plugin_class(config).client.statement_timeout
        == DATASOURCE_STATEMENT_TIMEOUT_SECONDS
    )
