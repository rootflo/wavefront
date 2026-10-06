"""
Datasource Tools Registry

Contains all datasource-related tools. Generic, type-agnostic tools only —
they call wavefront's own REST API, which already dispatches to the
appropriate datasource plugin (Postgres/BigQuery/Redshift/MSSQL) internally.
"""

from types import MethodType
from typing import Callable, Dict

from tools_module.datasources.datasource_api_tools import (
    datasource_insert_rows,
    datasource_insert_multi,
    datasource_execute_query,
)
from tools_module.floware_api import FlowareApiClient


def build_datasource_registry(api: FlowareApiClient) -> Dict[str, Callable]:
    """Datasource tools bound to the floware API they should call."""
    return {
        'datasource_insert_rows': MethodType(datasource_insert_rows, api),
        'datasource_insert_multi': MethodType(datasource_insert_multi, api),
        'datasource_execute_query': MethodType(datasource_execute_query, api),
    }
