"""
Tests for how datasource plugins run the queries of one dynamic-query YAML
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from datasource.bigquery import BigQueryPlugin
from datasource.mssql import MSSQLPlugin
from datasource.postgres import PostgresPlugin
from datasource.redshift import RedshiftPlugin


def _plugin(cls):
    # Skip the constructors, which would build real clients.
    plugin = object.__new__(cls)
    plugin.config = SimpleNamespace(schema='public')
    plugin.client = MagicMock()
    plugin.table_prefix = 'project.dataset.'
    return plugin


def _run_query_mock(plugin):
    """The blocking client call each plugin makes per query."""
    if isinstance(plugin, BigQueryPlugin):
        return plugin.client.query_rows
    return plugin.client.execute_query_as_dict


ALL_PLUGINS = [PostgresPlugin, MSSQLPlugin, RedshiftPlugin, BigQueryPlugin]


def _queries(*queries):
    return [
        {'id': query_id, 'query': sql, 'parameters': [{'name': p} for p in names]}
        for query_id, sql, names in queries
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize('cls', ALL_PLUGINS, ids=lambda c: c.__name__)
async def test_invalid_query_stops_the_batch_before_anything_runs(cls):
    plugin = _plugin(cls)
    queries = _queries(
        ('first', 'SELECT 1', []),
        ('second', 'SELECT :missing', ['missing']),
    )

    with pytest.raises(ValueError, match='Missing parameter'):
        await plugin.execute_dynamic_query(query=queries, params={})

    _run_query_mock(plugin).assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('cls', ALL_PLUGINS, ids=lambda c: c.__name__)
async def test_one_failing_query_does_not_fail_the_others(cls):
    plugin = _plugin(cls)

    def run(sql, params):
        if 'boom' in sql:
            raise RuntimeError('canceling statement due to statement timeout')
        return [{'sql': sql}]

    _run_query_mock(plugin).side_effect = run
    queries = _queries(
        ('ok_1', 'SELECT 1', []),
        ('bad', 'SELECT boom', []),
        ('ok_2', 'SELECT 2', []),
    )

    results = await plugin.execute_dynamic_query(query=queries, params={})

    assert list(results) == ['ok_1', 'bad', 'ok_2']
    assert results['ok_1']['status'] == 'success'
    assert results['ok_2']['status'] == 'success'
    assert results['bad']['status'] == 'error'
    assert results['bad']['result'] == []
