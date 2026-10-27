"""
Tests for per-datasource table name validation on the read path
"""

from unittest.mock import MagicMock

import pytest
from datasource import DatasourcePlugin, InvalidResourceError
from datasource.bigquery import BigQueryPlugin
from datasource.dialect import BigQuerySqlDialect, PostgresSqlDialect
from datasource.mssql import MSSQLPlugin
from datasource.odata_parser import ODataQueryParser
from datasource.postgres import PostgresPlugin
from datasource.redshift import RedshiftPlugin

# validate_table_name touches no client state, so skip the constructors that
# would open connections.
DEFAULT_RULE_PLUGINS = [
    object.__new__(PostgresPlugin),
    object.__new__(RedshiftPlugin),
    object.__new__(MSSQLPlugin),
]
bigquery = object.__new__(BigQueryPlugin)

INJECTIONS = [
    'users; DROP TABLE users',
    'users WHERE 1=1',
    "users'",
    'a.b.c',
    '',
]


@pytest.mark.parametrize('plugin', DEFAULT_RULE_PLUGINS)
@pytest.mark.parametrize('name', ['kyc_live_events', 'public.kyc_live_events', '_t1'])
def test_default_rule_accepts_identifiers(plugin, name):
    plugin.validate_table_name(name)


@pytest.mark.parametrize('plugin', DEFAULT_RULE_PLUGINS)
@pytest.mark.parametrize(
    'name', INJECTIONS + ['users--', 'my-table', '1table', 'x' * 513]
)
def test_default_rule_rejects_unsafe_names(plugin, name):
    with pytest.raises(InvalidResourceError):
        plugin.validate_table_name(name)


@pytest.mark.parametrize('name', ['events', 'my-table', '2024_events', 'ds.my-table'])
def test_bigquery_accepts_hyphenated_ids(name):
    bigquery.validate_table_name(name)


@pytest.mark.parametrize('name', INJECTIONS + ['tbl`', '`tbl`', 'x' * 1025])
def test_bigquery_rejects_unsafe_names(name):
    with pytest.raises(InvalidResourceError):
        bigquery.validate_table_name(name)


def _facade(plugin, dialect, dynamic_var_char):
    facade = object.__new__(DatasourcePlugin)
    plugin.fetch_data = MagicMock(return_value=[])
    facade.datasource = plugin
    facade.odata_parser = ODataQueryParser(
        type='sql', dynamic_var_char=dynamic_var_char, dialect=dialect
    )
    return facade


def test_fetch_data_rejects_invalid_base_table_before_querying():
    plugin = object.__new__(PostgresPlugin)
    facade = _facade(plugin, PostgresSqlDialect(), ':')

    with pytest.raises(InvalidResourceError):
        facade.fetch_data(table_name='users; DROP TABLE users')
    plugin.fetch_data.assert_not_called()


def test_fetch_data_uses_datasource_specific_rule():
    plugin = object.__new__(BigQueryPlugin)
    facade = _facade(plugin, BigQuerySqlDialect(), '@')

    facade.fetch_data(table_name='my-table')
    assert plugin.fetch_data.call_args.kwargs['table_names'] == ['my-table']


def test_invalid_resource_error_is_a_value_error():
    assert issubclass(InvalidResourceError, ValueError)


BAD = 'users; DROP TABLE users'


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
