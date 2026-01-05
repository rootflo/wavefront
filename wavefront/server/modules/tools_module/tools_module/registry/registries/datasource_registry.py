"""
Datasource Tools Registry

Contains all datasource-related tools including BigQuery, PostgreSQL, MySQL, etc.
"""

from tools_module.datasources.bigquery_tools import (
    bigquery_test_connection,
    bigquery_get_schema,
    bigquery_get_table_names,
    bigquery_insert_rows,
    bigquery_execute_query,
)

# BigQuery Tools Registry
BIGQUERY_REGISTRY = {
    'bigquery_test_connection': bigquery_test_connection,
    'bigquery_get_schema': bigquery_get_schema,
    'bigquery_get_table_names': bigquery_get_table_names,
    'bigquery_insert_rows': bigquery_insert_rows,
    'bigquery_execute_query': bigquery_execute_query,
}

# TODO: Add other datasource registries as they are implemented
# REDSHIFT_REGISTRY = {}

# Combined datasource registry
DATASOURCE_REGISTRY = {
    **BIGQUERY_REGISTRY,
    # **REDSHIFT_REGISTRY,
}
