from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from ..types import DataSourceABC
from .config import BigQueryConfig
from flo_cloud.gcp.bigquery import BigQueryClient
import asyncio


class BigQueryPlugin(DataSourceABC):
    def __init__(self, config: BigQueryConfig):
        self.config = config
        self.client = BigQueryClient(
            project_id=config.project_id,
            location=config.location,
            credentials_path=config.credentials_path,
            credentials_json=config.credentials_json,
        )
        self.table_prefix = f'{config.project_id}.{config.dataset_id}.'

    async def test_connection(self) -> bool:
        return await self.client.test_connection()

    def get_schema(self) -> dict:
        tables = self.client.list_tables(self.config.dataset_id)
        return {
            table.table_id: (
                self.client.get_table_info(self.config.dataset_id, table.table_id).get(
                    'schema'
                )
                or {}
            )
            for table in tables
        }

    def get_table_names(self, **kwargs) -> list[str]:
        dataset_id = kwargs.get('dataset_id', self.config.dataset_id)
        tables = self.client.list_tables(dataset_id)
        return [table.table_id for table in tables]

    def fetch_data(
        self,
        table_names: List[str],
        projection: Optional[str] = '*',
        where_clause: Optional[str] = 'true',
        join_query: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        offset: Optional[int] = 0,
        limit: Optional[int] = 1000,
        order_by: Optional[str] = None,
        group_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        projection_value = projection or '*'
        where_clause_value = where_clause or 'true'
        limit_value = limit if limit is not None else 1000
        offset_value = offset if offset is not None else 0

        result = self.client.execute_query_to_dict(
            projection=projection_value,
            table_prefix=self.table_prefix,
            table_names=table_names,
            where_clause=where_clause_value,
            join_query=join_query,
            params=params,
            limit=limit_value,
            offset=offset_value,
            order_by=order_by,
            group_by=group_by,
        )
        return result

    def insert_rows_json(self, table_name: str, data: List[Dict[str, Any]]):
        result = self.client.insert_rows_json(f'{self.table_prefix}{table_name}', data)
        return result

    async def execute_query(
        self, query: str, use_legacy_sql: bool = False, dry_run: bool = False, **kwargs
    ) -> Any:
        # Set default dataset for unqualified table names using QueryJobConfig
        dataset_path = self.table_prefix.rstrip('.')
        kwargs['default_dataset'] = dataset_path

        result = await self.client.execute_query(
            query, use_legacy_sql, dry_run, **kwargs
        )
        return result

    async def execute_dynamic_query(
        self,
        query: List[Dict[str, Any]],
        odata_filter: Optional[str] = None,
        odata_params: Optional[Dict[str, Any]] = None,
        odata_data_filter: Optional[str] = None,
        odata_data_params: Optional[Dict[str, Any]] = None,
        offset: Optional[int] = 0,
        limit: Optional[int] = 100,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        results = {}
        tasks = []

        for query_obj in query:
            query_to_execute = query_obj.get('query', '')
            query_params = query_obj.get('parameters', [])
            query_id = query_obj.get('id')
            if not query_id:
                raise ValueError('Query ID is required')

            params_key = [params['name'] for params in query_params]
            param_types = {
                params['name']: (
                    params.get('type') if isinstance(params, dict) else None
                )
                for params in query_params
            }
            params_to_execute = dict()

            # Handle case when params is None
            if params is None:
                params = {}

            for key in params_key:
                if key not in params:
                    raise ValueError(f'Missing parameter: {key} for query {query_id}')
                value = params[key]
                # If the YAML declares this param as TIMESTAMP, parse common
                # scheduler-generated values into Python datetime so the
                # BigQuery client binds as TIMESTAMP (not STRING).
                if param_types.get(key) == 'timestamp' and isinstance(value, str):
                    # Expected format from scheduler: 'YYYY-MM-DD HH:MM:SS' (UTC).
                    try:
                        value_dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                        params_to_execute[key] = value_dt.replace(tzinfo=timezone.utc)
                    except Exception:
                        params_to_execute[key] = value
                else:
                    params_to_execute[key] = value

            if odata_params:
                params_to_execute.update(odata_params)
            if odata_data_params:
                params_to_execute.update(odata_data_params)

            # Replace placeholders in the query
            query_to_execute = query_to_execute.replace(
                '{{rls}}', f'{odata_data_filter}' if odata_data_filter else 'TRUE'
            )
            query_to_execute = query_to_execute.replace(
                '{{filters}}', f'{odata_filter}' if odata_filter else 'TRUE'
            )
            # adding limit and offset to the query
            query_to_execute += f' LIMIT {limit} OFFSET {offset}'

            # Create async task for query execution
            task = asyncio.create_task(
                self.client.execute_query(query_to_execute, params=params_to_execute)
            )
            tasks.append((query_obj['id'], task))

        for query_id, task in tasks:
            try:
                # Await the async task to get the QueryJob
                query_job = await task

                query_result = list(query_job.result())
                formatted_result = [dict(row.items()) for row in query_result]

                results[query_id] = {
                    'status': 'success',
                    'error': None,
                    'description': f'Query {query_id} executed successfully',
                    'result': formatted_result,
                }
            except Exception as e:
                results[query_id] = {
                    'status': 'error',
                    'error': str(e),
                    'description': f'Error executing query {query_id}',
                    'result': [],
                }

        return results


__all__ = ['BigQueryPlugin', 'BigQueryConfig']
