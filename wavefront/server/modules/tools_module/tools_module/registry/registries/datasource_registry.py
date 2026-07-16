"""
Datasource Tools Registry

Contains all datasource-related tools. Generic, type-agnostic tools only —
they call wavefront's own REST API, which already dispatches to the
appropriate datasource plugin (Postgres/BigQuery/Redshift/MSSQL) internally.
"""

from tools_module.datasources.datasource_api_tools import (
    datasource_insert_rows,
)

# Combined datasource registry
DATASOURCE_REGISTRY = {
    'datasource_insert_rows': datasource_insert_rows,
}
