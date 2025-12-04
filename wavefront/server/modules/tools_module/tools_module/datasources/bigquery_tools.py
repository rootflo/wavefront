import asyncio
from typing import Any, Dict, List, Optional, cast

from datasource import BigQueryConfig, DataSourceType
from datasource.bigquery import BigQueryPlugin
from plugins_module.services.datasource_services import get_datasource_config


async def bigquery_test_connection(datasource_id: str) -> str:
    """Test BigQuery connection using configured datasource"""
    try:
        # Get datasource config from database
        ds_type, config = await get_datasource_config(datasource_id)

        if not config:
            return f"❌ Datasource '{datasource_id}' not found"

        if ds_type != DataSourceType.GCP_BIGQUERY:
            return f"❌ Invalid datasource type '{ds_type}' for BigQuery tool"

        bq_config = cast(BigQueryConfig, config)
        plugin = BigQueryPlugin(bq_config)
        result = plugin.test_connection()

        if result:
            return f"✅ Successfully connected to BigQuery project '{bq_config.project_id}', dataset '{bq_config.dataset_id}' in location '{bq_config.location}'"
        else:
            return f"❌ Failed to connect to BigQuery project '{bq_config.project_id}', dataset '{bq_config.dataset_id}' in location '{bq_config.location}'"
    except Exception as e:
        return f"❌ Connection error for datasource '{datasource_id}': {str(e)}"


async def bigquery_get_schema(datasource_id: str, table_id: str) -> str:
    """Get BigQuery dataset schema information using configured datasource"""
    try:
        # Get datasource config from database
        ds_type, config = await get_datasource_config(datasource_id)

        if not config:
            return f"❌ Datasource '{datasource_id}' not found"

        if ds_type != DataSourceType.GCP_BIGQUERY:
            return f"❌ Invalid datasource type '{ds_type}' for BigQuery tool"

        bq_config = cast(BigQueryConfig, config)
        plugin = BigQueryPlugin(bq_config)
        schema_info = plugin.get_schema(table_id)

        if not schema_info:
            return f"No schema information available for dataset '{bq_config.dataset_id}' in project '{bq_config.project_id}'"

        # Format schema information as readable text
        result = f"📊 Schema for dataset '{bq_config.dataset_id}' in project '{bq_config.project_id}':\n\n"

        result += str(schema_info)

        return result
    except Exception as e:
        return f"❌ Error retrieving schema for datasource '{datasource_id}': {str(e)}"


async def bigquery_get_table_names(datasource_id: str) -> str:
    """Get list of table names from BigQuery dataset using configured datasource"""
    try:
        # Get datasource config from database
        ds_type, config = await get_datasource_config(datasource_id)

        if not config:
            return f"❌ Datasource '{datasource_id}' not found"

        if ds_type != DataSourceType.GCP_BIGQUERY:
            return f"❌ Invalid datasource type '{ds_type}' for BigQuery tool"

        bq_config = cast(BigQueryConfig, config)
        plugin = BigQueryPlugin(bq_config)
        table_names = plugin.get_table_names()

        if not table_names:
            return f"No tables found in dataset '{bq_config.dataset_id}' in project '{bq_config.project_id}'"

        result = f"📋 Found {len(table_names)} table(s) in dataset '{bq_config.dataset_id}' (project '{bq_config.project_id}'):\n\n"

        for i, table_name in enumerate(table_names, 1):
            result += f'{i}. {table_name}\n'

        return result
    except Exception as e:
        return f"❌ Error retrieving table names for datasource '{datasource_id}': {str(e)}"


async def bigquery_fetch_data(
    datasource_id: str,
    table_names: List[str],
    projection: str = '*',
    where_clause: str = 'true',
    join_query: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
    offset: int = 0,
    limit: int = 1000,
    order_by: Optional[str] = None,
    group_by: Optional[str] = None,
) -> str:
    """Fetch data from BigQuery tables using configured datasource with optional filtering and joins"""
    try:
        # Get datasource config from database
        ds_type, config = await get_datasource_config(datasource_id)

        if not config:
            return f"❌ Datasource '{datasource_id}' not found"

        if ds_type != DataSourceType.GCP_BIGQUERY:
            return f"❌ Invalid datasource type '{ds_type}' for BigQuery tool"

        bq_config = cast(BigQueryConfig, config)
        plugin = BigQueryPlugin(bq_config)
        results = plugin.fetch_data(
            table_names=table_names,
            projection=projection,
            where_clause=where_clause,
            join_query=join_query,
            params=params,
            offset=offset,
            limit=limit,
            order_by=order_by,
            group_by=group_by,
        )

        if not results:
            table_list = ', '.join(table_names)
            return (
                f"No data found in table(s) '{table_list}' matching the query criteria"
            )

        table_list = ', '.join(table_names)
        result = f"📊 Retrieved {len(results)} record(s) from table(s) '{table_list}' in dataset '{bq_config.dataset_id}':\n\n"

        # Show first few records
        display_limit = min(5, len(results))

        if results and isinstance(results[0], dict):
            # Get column headers from first record
            headers = list(results[0].keys())
            result += 'Columns: ' + ', '.join(headers) + '\n\n'

            for i, row in enumerate(results[:display_limit], 1):
                result += f'Record {i}:\n'
                for key, value in row.items():
                    # Truncate long values
                    str_value = str(value)
                    if len(str_value) > 100:
                        str_value = str_value[:100] + '...'
                    result += f'  {key}: {str_value}\n'
                result += '\n'

        if len(results) > display_limit:
            result += f'... and {len(results) - display_limit} more record(s)\n'

        # Add query details
        result += '\nQuery details:\n'
        result += f'  Projection: {projection}\n'
        result += f'  Where: {where_clause}\n'
        result += f'  Limit: {limit}\n'
        result += f'  Offset: {offset}\n'
        if order_by:
            result += f'  Order by: {order_by}\n'

        return result
    except Exception as e:
        table_list = ', '.join(table_names)
        return f"❌ Error fetching data from table(s) '{table_list}' for datasource '{datasource_id}': {str(e)}"


async def bigquery_insert_rows(
    datasource_id: str, table_name: str, data: List[Dict[str, Any]]
) -> str:
    """Insert rows into BigQuery table using configured datasource"""
    try:
        # Get datasource config from database
        ds_type, config = await get_datasource_config(datasource_id)

        if not config:
            return f"❌ Datasource '{datasource_id}' not found"

        if ds_type != DataSourceType.GCP_BIGQUERY:
            return f"❌ Invalid datasource type '{ds_type}' for BigQuery tool"
        bq_config = cast(BigQueryConfig, config)
        plugin = BigQueryPlugin(bq_config)

        if not data:
            return f"No data provided for insertion into table '{table_name}'"

        result = plugin.insert_rows_json(table_name, data)

        # Check if insertion was successful
        if result is None or (isinstance(result, list) and len(result) == 0):
            # Success case (empty errors list means success)
            return f"✅ Successfully inserted {len(data)} record(s) into table '{table_name}' in dataset '{bq_config.dataset_id}' (project '{bq_config.project_id}')"
        else:
            # Handle error cases
            if isinstance(result, list) and len(result) > 0:
                error_details = '; '.join(
                    [str(error) for error in result[:3]]
                )  # Show first 3 errors
                more_errors = f' and {len(result) - 3} more' if len(result) > 3 else ''
                return f"❌ Failed to insert some records into table '{table_name}': {error_details}{more_errors}"
            else:
                return f'⚠️ Insertion completed with result: {str(result)}'

    except Exception as e:
        return f"❌ Error inserting records for datasource '{datasource_id}', table '{table_name}': {str(e)}"


async def bigquery_execute_query(
    datasource_id: str, query: str, use_legacy_sql: bool = False, dry_run: bool = False
) -> str:
    """Execute a BigQuery SQL query using configured datasource"""
    try:
        # Get datasource config from database
        ds_type, config = await get_datasource_config(datasource_id)

        if not config:
            return f"Datasource '{datasource_id}' not found"

        if ds_type != DataSourceType.GCP_BIGQUERY:
            return f"Invalid datasource type '{ds_type}' for BigQuery tool"

        bq_config = cast(BigQueryConfig, config)
        plugin = BigQueryPlugin(bq_config)

        if not query or not query.strip():
            return '❌ No query provided for execution'

        result = await plugin.execute_query(
            query, use_legacy_sql=use_legacy_sql, dry_run=dry_run
        )

        if dry_run:
            # For dry run, return query validation info
            return f"✅ Query validation successful for project '{bq_config.project_id}'. Query is valid and ready to execute."
        else:
            # For actual execution, get results and format response
            job_id = getattr(result, 'job_id', 'unknown')

            try:
                # Get query results if available
                # result.result() is a blocking call, so run it in a thread pool
                query_results = await asyncio.to_thread(
                    lambda: list(result.result())
                )  # Convert iterator to list

                if query_results:
                    # Format results similar to bigquery_fetch_data
                    response = f"✅ Query executed successfully in project '{bq_config.project_id}' (Job ID: {job_id})\n\n"
                    response += f'📊 Retrieved {len(query_results)} record(s):\n\n'

                    # Show first few records
                    display_limit = min(5, len(query_results))

                    if query_results and len(query_results[0]) > 0:
                        # Get column headers from first record
                        headers = (
                            list(query_results[0].keys())
                            if hasattr(query_results[0], 'keys')
                            else [f'col_{i}' for i in range(len(query_results[0]))]
                        )
                        response += 'Columns: ' + ', '.join(headers) + '\n\n'

                        for i, row in enumerate(query_results[:display_limit], 1):
                            response += f'Record {i}:\n'
                            if hasattr(row, 'items'):  # Row object with key-value pairs
                                for key, value in row.items():
                                    str_value = str(value)
                                    if len(str_value) > 100:
                                        str_value = str_value[:100] + '...'
                                    response += f'  {key}: {str_value}\n'
                            else:  # Simple tuple/list row
                                for j, value in enumerate(row):
                                    str_value = str(value)
                                    if len(str_value) > 100:
                                        str_value = str_value[:100] + '...'
                                    response += f"  {headers[j] if j < len(headers) else f'col_{j}'}: {str_value}\n"
                            response += '\n'

                    if len(query_results) > display_limit:
                        response += f'... and {len(query_results) - display_limit} more record(s)\n'

                    return response
                else:
                    # No results (e.g., INSERT, UPDATE, DELETE, DDL statements)
                    num_affected = getattr(result, 'num_dml_affected_rows', None)
                    if num_affected is not None:
                        return f"✅ Query executed successfully in project '{bq_config.project_id}' (Job ID: {job_id})\nAffected rows: {num_affected}"
                    else:
                        return f"✅ Query executed successfully in project '{bq_config.project_id}' (Job ID: {job_id})"

            except Exception as result_error:
                # If we can't get results, just return success with job info
                return f"✅ Query executed successfully in project '{bq_config.project_id}' (Job ID: {job_id})\n⚠️ Could not retrieve results: {str(result_error)}"

    except Exception as e:
        error_msg = str(e).lower()

        # Enhanced error handling for common BigQuery issues
        if 'table' in error_msg and 'not found' in error_msg:
            return f"❌ Table not found. Please check that the table exists in dataset '{bq_config.dataset_id}' of project '{bq_config.project_id}'. Error: {str(e)}"
        elif 'dataset' in error_msg and 'not found' in error_msg:
            return f"❌ Dataset '{bq_config.dataset_id}' not found in project '{bq_config.project_id}'. Please check your datasource configuration. Error: {str(e)}"
        elif 'permission' in error_msg or 'access' in error_msg:
            return f"❌ Permission denied. Please check your BigQuery credentials and access rights to project '{bq_config.project_id}' and dataset '{bq_config.dataset_id}'. Error: {str(e)}"
        elif 'syntax error' in error_msg or 'invalid query' in error_msg:
            return f"❌ SQL syntax error. Please check your query syntax. Note: Table names are automatically qualified with dataset '{bq_config.dataset_id}'. Error: {str(e)}"
        elif 'quota' in error_msg or 'exceeded' in error_msg:
            return f'❌ BigQuery quota or limits exceeded. Please try again later or contact your administrator. Error: {str(e)}'
        else:
            return (
                f"❌ Error executing query for datasource '{datasource_id}': {str(e)}"
            )
