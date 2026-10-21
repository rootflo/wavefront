"""
Datasource Tools Registry

Contains all datasource-related tools. They call wavefront's own REST API,
which dispatches to the appropriate datasource plugin internally: SQL tools
for Postgres/BigQuery/Redshift/MSSQL, file tools for S3/GCS/Azure Blob.
"""

from types import MethodType
from typing import Callable, Dict

from tools_module.datasources.datasource_api_tools import (
    datasource_insert_rows,
    datasource_insert_multi,
    datasource_execute_query,
    datasource_download_file,
)
from tools_module.floware_api import FlowareApiClient


def build_datasource_registry(api: FlowareApiClient) -> Dict[str, Callable]:
    """Datasource tools bound to the floware API they should call."""
    return {
        'datasource_insert_rows': MethodType(datasource_insert_rows, api),
        'datasource_insert_multi': MethodType(datasource_insert_multi, api),
        'datasource_execute_query': MethodType(datasource_execute_query, api),
        'datasource_download_file': MethodType(datasource_download_file, api),
    }
