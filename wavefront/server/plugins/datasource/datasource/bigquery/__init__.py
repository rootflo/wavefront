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

    def get_schema(self, table_id: str) -> dict:
        table_info = self.client.get_table_info(self.config.dataset_id, table_id)
        return table_info['schema'] or {}

    def get_table_names(self, **kwargs) -> list[str]:
        dataset_id = kwargs.get('dataset_id', self.config.dataset_id)
        tables = self.client.list_tables(dataset_id)
        return [table.table_id for table in tables]

    def fetch_data(
        self,
        table_names: List[str],
        projection: str = '*',
        where_clause: str = 'true',
        join_query: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        offset: int = 0,
        limit: int = 1000,
        order_by: Optional[str] = None,
        group_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        result = self.client.execute_query_to_dict(
            projection=projection,
            table_prefix=self.table_prefix,
            table_names=table_names,
            where_clause=where_clause,
            join_query=join_query,
            params=params,
            limit=limit,
            offset=offset,
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
        queries: List[Dict[str, Any]],
        offset: Optional[int] = 0,
        limit: Optional[int] = 100,
        odata_filter: Optional[str] = None,
        odata_params: Optional[Dict[str, Any]] = None,
        odata_data_filter: Optional[str] = None,
        odata_data_params: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ):
        results = {}
        tasks = []

        for query_obj in queries:
            query_to_execute = query_obj.get('query', '')
            query_params = query_obj.get('parameters', {})
            query_id = query_obj.get('id')
            if not query_id:
                raise ValueError('Query ID is required')

            params_key = [params['name'] for params in query_params]
            params_to_execute = dict()

            # Handle case when params is None
            if params is None:
                params = {}

            for key in params_key:
                if key not in params:
                    raise ValueError(f'Missing parameter: {key} for query {query_id}')
                params_to_execute[key] = params[key]

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
