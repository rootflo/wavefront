from typing import Any, Dict, List, Optional

from ..executor import (
    current_statement_timeout,
    limits,
    run_blocking,
    run_blocking_batch,
)
from ..types import DataSourceABC
from flo_cloud.aws.redshift import RedshiftClient as AWSRedshiftClient
from .config import RedshiftConfig


class RedshiftPlugin(DataSourceABC):
    def __init__(self, config: RedshiftConfig):
        self.config = config
        self.client = AWSRedshiftClient(
            host=config.host,
            port=config.port,
            database=config.database,
            user=config.user,
            password=config.password,
            timeout=limits().connect_timeout_seconds,
            statement_timeout=current_statement_timeout(),
        )
        self.db_name = f'{config.database}.public'

    async def test_connection(self) -> bool:
        return await run_blocking(self.client.test_connection)

    def get_schema(self) -> dict:
        table_names = self.client.list_tables()
        return {
            table_name: self.client.get_table_info(table_name)
            for table_name in table_names
        }

    def get_table_names(self, **kwargs) -> list[str]:
        return self.client.list_tables()

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
        projection_value = projection or '*'
        where_clause_value = where_clause or 'true'
        limit_value = limit if limit is not None else 10
        offset_value = offset if offset is not None else 0

        return self.client.execute_query_to_dict(
            projection=projection_value,
            table_prefix=f'{self.db_name}.',
            table_names=table_names,
            where_clause=where_clause_value,
            join_query=join_query,
            params=params,
            limit=limit_value,
            offset=offset_value,
            order_by=order_by,
            group_by=group_by,
        )

    def insert_rows_json(self, table_name: str, data: List[Dict[str, Any]]) -> None:
        self.client.insert_rows_json(f'{self.db_name}.{table_name}', data)

    async def execute_query(
        self, query: str, use_legacy_sql: bool = False, dry_run: bool = False, **kwargs
    ) -> Any:
        params = kwargs.get('params')
        return await run_blocking(self.client.execute_query_as_dict, query, params)

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
    ):
        results = {}
        prepared = []

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

            prepared.append((query_id, query_to_execute, params_to_execute))

        # Every query is validated above before any of them starts, so a bad
        # query further down cannot leave earlier ones running unobserved.
        outcomes = await run_blocking_batch(
            [
                (self.client.execute_query_as_dict, (sql, sql_params))
                for _, sql, sql_params in prepared
            ]
        )

        for (query_id, _, _), outcome in zip(prepared, outcomes):
            if isinstance(outcome, BaseException):
                results[query_id] = {
                    'status': 'error',
                    'error': str(outcome),
                    'description': f'Error executing query {query_id}',
                    'result': [],
                }
            else:
                results[query_id] = {
                    'status': 'success',
                    'error': None,
                    'description': f'Query {query_id} executed successfully',
                    'result': outcome,
                }

        return results


__all__ = ['RedshiftPlugin', 'RedshiftConfig']
