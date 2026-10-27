"""
Tests for per-datasource validation of table names and query clauses
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from datasource import DatasourcePlugin, InvalidQueryError, InvalidResourceError
from datasource.bigquery import BigQueryPlugin
from datasource.dialect import BigQuerySqlDialect, PostgresSqlDialect
from datasource.mssql import MSSQLPlugin
from datasource.odata_parser import ODataQueryParser
from datasource.postgres import PostgresPlugin
from datasource.redshift import RedshiftPlugin
from flo_cloud.postgres import PostgresClient


def _plugin(cls, schema=None):
    # Validation touches no client state, so skip the constructors that would
    # open connections.
    plugin = object.__new__(cls)
    plugin.config = SimpleNamespace(schema=schema)
    return plugin


postgres = _plugin(PostgresPlugin, schema='tenant')
mssql = _plugin(MSSQLPlugin, schema='sales')
redshift = _plugin(RedshiftPlugin)
bigquery = _plugin(BigQueryPlugin)
ALL_PLUGINS = [postgres, mssql, redshift, bigquery]

INJECTIONS = [
    'users; DROP TABLE users',
    'users WHERE 1=1',
    "users'",
    'a.b.c',
    '',
]


@pytest.mark.parametrize('plugin', ALL_PLUGINS)
@pytest.mark.parametrize('name', ['kyc_live_events', '_t1'])
def test_plain_identifiers_are_accepted(plugin, name):
    plugin.validate_table_name(name)


@pytest.mark.parametrize('plugin', [postgres, mssql, redshift])
@pytest.mark.parametrize(
    'name', INJECTIONS + ['users--', 'my-table', '1table', 'x' * 513]
)
def test_identifier_rule_rejects_unsafe_names(plugin, name):
    with pytest.raises(InvalidResourceError):
        plugin.validate_table_name(name)


@pytest.mark.parametrize(
    'plugin, name', [(postgres, 'tenant.orders'), (mssql, 'sales.orders')]
)
def test_configured_schema_prefix_is_accepted(plugin, name):
    plugin.validate_table_name(name)


@pytest.mark.parametrize('plugin', [postgres, mssql])
@pytest.mark.parametrize(
    'name',
    [
        'public.orders',
        'pg_catalog.pg_authid',
        'information_schema.tables',
        'sys.objects',
        '.orders',
        'tenant.sales.orders',
    ],
)
def test_other_schemas_are_rejected(plugin, name):
    with pytest.raises(InvalidResourceError):
        plugin.validate_table_name(name)


@pytest.mark.parametrize('name', ['public.orders', 'tenant.orders'])
def test_redshift_rejects_qualified_names(name):
    # Redshift reads and writes both prefix `{database}.public.` themselves.
    with pytest.raises(InvalidResourceError):
        redshift.validate_table_name(name)


@pytest.mark.parametrize('name', ['events', 'my-table', '2024_events', 'users--'])
def test_bigquery_accepts_hyphenated_ids(name):
    bigquery.validate_table_name(name)


@pytest.mark.parametrize(
    'name', INJECTIONS + ['ds.my-table', 'tbl`', '`tbl`', 'x' * 1025]
)
def test_bigquery_rejects_unsafe_names(name):
    with pytest.raises(InvalidResourceError):
        bigquery.validate_table_name(name)


@pytest.mark.parametrize('plugin', ALL_PLUGINS)
@pytest.mark.parametrize(
    'projection, order_by, group_by',
    [
        ('*', None, None),
        (None, None, None),
        ('id, name', 'created_at desc', None),
        ('user_id, users.name, current_user_id', 'user_id', 'user_id'),
        ('a.id, b.total', 'a.id ASC, b.total', None),
        ('orders.*, customers.name', None, None),
        ('status, count(*) as n', 'count(*) desc', 'status'),
        ('region, SUM(amount) total, avg(a.price)', 'total', 'region'),
        ('count(distinct customer_id) AS buyers', None, None),
    ],
)
def test_query_clauses_accept_columns_and_aggregates(
    plugin, projection, order_by, group_by
):
    plugin.validate_query_clauses(projection, order_by, group_by)


@pytest.mark.parametrize('plugin', ALL_PLUGINS)
@pytest.mark.parametrize(
    'projection, order_by, group_by',
    [
        ('(SELECT passwd FROM pg_shadow) AS x', None, None),
        ('id, (select 1)', None, None),
        ('current_user', None, None),
        ('id, SESSION_USER', None, None),
        ('*', 'current_schema', None),
        ('*', None, 'user'),
        ("pg_read_file('/etc/passwd')", None, None),
        ("'a' AS x", None, None),
        ('id -- comment', None, None),
        ('id; DROP TABLE users', None, None),
        ('id, ', None, None),
        ('a.b.c', None, None),
        ('*', 'id; DROP TABLE users', None),
        ('*', '(SELECT 1)', None),
        ('*', 'id desc nulls first', None),
        ('*', None, 'status, (select 1)'),
        ('*', None, 'count(*)'),
        pytest.param('id' + ', id' * 2000, None, None, id='too-long'),
    ],
)
def test_query_clauses_reject_expressions(plugin, projection, order_by, group_by):
    with pytest.raises(InvalidQueryError):
        plugin.validate_query_clauses(projection, order_by, group_by)


def _facade(plugin, dialect, dynamic_var_char):
    facade = object.__new__(DatasourcePlugin)
    plugin.fetch_data = MagicMock(return_value=[])
    facade.datasource = plugin
    facade.odata_parser = ODataQueryParser(
        type='sql', dynamic_var_char=dynamic_var_char, dialect=dialect
    )
    return facade


def test_fetch_data_rejects_invalid_base_table_before_querying():
    plugin = _plugin(PostgresPlugin, schema='tenant')
    facade = _facade(plugin, PostgresSqlDialect(), ':')

    with pytest.raises(InvalidResourceError):
        facade.fetch_data(table_name='users; DROP TABLE users')
    plugin.fetch_data.assert_not_called()


@pytest.mark.parametrize(
    'kwargs',
    [
        {'projection': '(SELECT usename FROM pg_user) AS u'},
        {'order_by': '(SELECT 1)'},
        {'group_by': 'id; DROP TABLE users'},
    ],
)
def test_fetch_data_rejects_invalid_clauses_before_querying(kwargs):
    plugin = _plugin(PostgresPlugin, schema='tenant')
    facade = _facade(plugin, PostgresSqlDialect(), ':')

    with pytest.raises(InvalidQueryError):
        facade.fetch_data(table_name='orders', **kwargs)
    plugin.fetch_data.assert_not_called()


def test_fetch_data_uses_datasource_specific_rule():
    plugin = _plugin(BigQueryPlugin)
    facade = _facade(plugin, BigQuerySqlDialect(), '@')

    facade.fetch_data(table_name='my-table')
    assert plugin.fetch_data.call_args.kwargs['table_names'] == ['my-table']


def test_validation_errors_are_value_errors():
    assert issubclass(InvalidResourceError, ValueError)
    assert issubclass(InvalidQueryError, ValueError)


BAD = 'pg_catalog.pg_authid'


@pytest.mark.parametrize(
    'call',
    [
        lambda f: f.insert_rows_json(BAD, [{'a': 1}]),
        lambda f: f.insert_rows_json_multi(
            [
                {'table_name': 'ok', 'data': [{'a': 1}]},
                {'table_name': BAD, 'data': [{'a': 1}]},
            ]
        ),
        lambda f: f.update_rows_json(BAD, {'a': 1}, "id eq '1'"),
        lambda f: f.update_rows_json_multi(
            [{'table_name': BAD, 'data': {'a': 1}, 'filter': "id eq '1'"}]
        ),
        lambda f: f.delete_rows_json(BAD, "id eq '1'"),
    ],
    ids=['insert', 'insert_multi', 'update', 'update_multi', 'delete'],
)
def test_write_operations_reject_invalid_table_before_writing(call):
    plugin = MagicMock(spec=PostgresPlugin)
    plugin.config = SimpleNamespace(schema='tenant')
    plugin.validate_table_name.side_effect = (
        lambda name: PostgresPlugin.validate_table_name(plugin, name)
    )
    facade = _facade(plugin, PostgresSqlDialect(), ':')

    with pytest.raises(InvalidResourceError):
        call(facade)
    for method in (
        'insert_rows_json',
        'insert_rows_json_multi',
        'update_rows_json',
        'update_rows_json_multi',
        'delete_rows_json',
    ):
        getattr(plugin, method).assert_not_called()


@pytest.mark.parametrize(
    'name, parts',
    [
        # Unqualified, 'pg_class' would resolve to pg_catalog ahead of search_path.
        ('pg_class', ('tenant', 'pg_class')),
        ('orders', ('tenant', 'orders')),
        ('tenant.orders', ('tenant', 'orders')),
    ],
)
def test_postgres_client_pins_write_targets_to_configured_schema(name, parts):
    client = PostgresClient(host='h', schema='tenant')
    assert client._table_identifier(name).strings == parts
