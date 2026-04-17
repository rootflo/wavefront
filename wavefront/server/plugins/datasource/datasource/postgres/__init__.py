import asyncio
from typing import Any, Dict, List, Optional

from ..types import DataSourceABC
from flo_cloud.postgres import PostgresClient
from .config import PostgresConfig


class PostgresPlugin(DataSourceABC):
    def __init__(self, config: PostgresConfig):
        self.config = config
        self.client = PostgresClient(
            host=config.host,
            port=config.port,
            database=config.database,
            user=config.user,
            password=config.password,
            schema=config.schema,
        )
        self.db_name = f'{config.database}.{config.schema}'

    async def test_connection(self) -> bool:
        return await asyncio.to_thread(self.client.test_connection)

    def get_schema(self) -> dict:
        table_names = self.client.list_tables()
        return {
            table_name: self.client.get_table_info(table_name)
            for table_name in table_names
        }

    def get_table_names(self, **kwargs) -> list[str]:
        schema = kwargs.get('schema', self.config.schema)
        return self.client.list_tables(schema=schema)

    def fetch_data(
        self,
        table_names: List[str],
        projection: Optional[str] = '*',
        where_clause: Optional[str] = 'true',
        join_query: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        offset: Optional[int] = 0,
        limit: Optional[int] = 10,
        order_by: Optional[str] = None,
        group_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return self.client.execute_query_to_dict(
            projection=projection or '*',
            table_prefix=f'{self.config.schema}.',
            table_names=table_names,
            where_clause=where_clause or 'true',
            join_query=join_query,
            params=params,
            limit=limit if limit is not None else 10,
            offset=offset if offset is not None else 0,
            order_by=order_by,
            group_by=group_by,
        )

    def insert_rows_json(self, table_name: str, data: List[Dict[str, Any]]) -> None:
        self.client.insert_rows_json(table_name, data)

    async def execute_query(
        self, query: str, use_legacy_sql: bool = False, dry_run: bool = False, **kwargs
    ) -> Any:
        params = kwargs.get('params')
        return await asyncio.to_thread(self.client.execute_query_as_dict, query, params)

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
            query_params = query_obj.get('parameters', {})
            query_id = query_obj.get('id')
            if not query_id:
                raise ValueError('Query ID is required')

            params_key = [p['name'] for p in query_params]
            params_to_execute: Dict[str, Any] = {}

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

            query_to_execute = query_to_execute.replace(
                '{{rls}}', f'{odata_data_filter}' if odata_data_filter else 'TRUE'
            )
            query_to_execute = query_to_execute.replace(
                '{{filters}}', f'{odata_filter}' if odata_filter else 'TRUE'
            )
            query_to_execute += f' LIMIT {limit} OFFSET {offset}'

            task = asyncio.create_task(
                asyncio.to_thread(
                    self.client.execute_query_as_dict,
                    query_to_execute,
                    params_to_execute,
                )
            )
            tasks.append((query_id, task))

        for query_id, task in tasks:
            try:
                formatted_result = await task
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


__all__ = ['PostgresPlugin', 'PostgresConfig']
