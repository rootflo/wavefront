from .types import (
    BooleanResult,
    DataSourceABC,
    DataSourceType,
    TableListResult,
    QueryResult,
)
from typing import Any, Optional, List, Dict

from .bigquery import BigQueryPlugin, BigQueryConfig
from .redshift import RedshiftPlugin, RedshiftConfig
from .postgres import PostgresPlugin, PostgresConfig
from .mssql import MSSQLPlugin, MSSQLConfig
from .helper import construct_meta
from .odata_parser import ODataQueryParser


class DatasourcePlugin:
    def __init__(
        self,
        datasource_type: DataSourceType,
        config: BigQueryConfig | RedshiftConfig | PostgresConfig | MSSQLConfig,
    ):
        self.datasource_type = datasource_type
        self.config = config
        self.datasource = self.__get_datasource()

    def __get_datasource(self) -> DataSourceABC:
        if self.datasource_type == DataSourceType.AWS_REDSHIFT:
            self.odata_parser = ODataQueryParser(type='sql', dynamic_var_char=':')
            if not isinstance(self.config, RedshiftConfig):
                raise ValueError(f'Invalid config type: {type(self.config)}')
            return RedshiftPlugin(self.config)
        elif self.datasource_type == DataSourceType.GCP_BIGQUERY:
            self.odata_parser = ODataQueryParser(type='sql', dynamic_var_char='@')
            if not isinstance(self.config, BigQueryConfig):
                raise ValueError(f'Invalid config type: {type(self.config)}')
            return BigQueryPlugin(self.config)
        elif self.datasource_type == DataSourceType.POSTGRES:
            self.odata_parser = ODataQueryParser(type='sql', dynamic_var_char=':')
            if not isinstance(self.config, PostgresConfig):
                raise ValueError(f'Invalid config type: {type(self.config)}')
            return PostgresPlugin(self.config)
        elif self.datasource_type == DataSourceType.MSSQL:
            self.odata_parser = ODataQueryParser(type='sql', dynamic_var_char=':')
            if not isinstance(self.config, MSSQLConfig):
                raise ValueError(f'Invalid config type: {type(self.config)}')
            return MSSQLPlugin(self.config)
        else:
            raise ValueError(f'Invalid datasource type: {self.datasource_type}')

    async def test_connection(self) -> BooleanResult:
        return BooleanResult(
            result=await self.datasource.test_connection(),
            meta=construct_meta(status='success', code=1),
        )

    def get_schema(self) -> dict:
        return self.datasource.get_schema()

    def get_table_names(self, **kwargs) -> TableListResult:
        result = self.datasource.get_table_names(**kwargs)
        return TableListResult(
            result=result, meta=construct_meta(status='success', code=1)
        )

    def fetch_data(
        self,
        table_name: str,
        projection: Optional[str] = '*',
        filter: Optional[str] = None,
        join: Optional[str] = None,
        offset: Optional[int] = 0,
        limit: Optional[int] = 10,
        order_by: Optional[str] = None,
        group_by: Optional[str] = None,
    ) -> QueryResult:
        where_clause, params = self.odata_parser.prepare_odata_filter(filter)
        join_query, table_aliases, join_where_clause, join_params = (
            self.odata_parser.prepare_odata_joins(join or '', table_name)
        )

        # '1=1' is a no-op predicate valid across all supported SQL dialects
        # (Postgres/Redshift/BigQuery and MSSQL, which has no `true` literal).
        where_clause = where_clause if where_clause else '1=1'
        if join_where_clause:
            where_clause = f'{where_clause} AND {join_where_clause}'
        params = (params if params else {}) | join_params

        result = self.datasource.fetch_data(
            table_names=[table_name] + table_aliases,
            projection=projection,
            where_clause=where_clause,
            join_query=join_query if join_query else None,
            params=params,
            offset=offset,
            limit=limit,
            order_by=order_by,
            group_by=group_by,
        )
        return QueryResult(result=result, meta=construct_meta(status='success', code=1))

    def insert_rows_json(self, table_name: str, data: List[Dict[str, Any]]):
        return self.datasource.insert_rows_json(table_name, data)

    def insert_rows_json_multi(self, inserts: List[Dict[str, Any]]):
        return self.datasource.insert_rows_json_multi(inserts)

    def update_rows_json(
        self, table_name: str, data: Dict[str, Any], filter: str
    ) -> int:
        """Update the rows matching the OData ``filter``, returning how many changed.

        Unlike ``fetch_data``, which falls back to a '1=1' no-op predicate when no
        filter is given, an absent or unparseable filter is an error here: an
        UPDATE with no WHERE rewrites the whole table, so it must never be
        reachable by omission.
        """
        where_clause, params = self.odata_parser.prepare_odata_filter(filter)
        if not where_clause:
            raise ValueError('A filter is required to update rows')
        return self.datasource.update_rows_json(
            table_name, data, where_clause, params or {}
        )

    def update_rows_json_multi(
        self, updates: List[Dict[str, Any]], require_all_matched: bool = True
    ) -> List[Dict[str, Any]]:
        """Update rows across several tables atomically.

        ``updates``: list of ``{"table_name", "data", "filter"}``, where ``filter``
        is OData. Each entry carries its own filter — the tables are related, not
        identical, so one predicate could not address them all.
        """
        prepared = []
        for update in updates:
            where_clause, params = self.odata_parser.prepare_odata_filter(
                update.get('filter')
            )
            if not where_clause:
                raise ValueError(
                    'A filter is required to update rows, missing for table '
                    f'{update.get("table_name")}'
                )
            prepared.append(
                {
                    'table_name': update['table_name'],
                    'data': update['data'],
                    'where_clause': where_clause,
                    'params': params or {},
                }
            )
        return self.datasource.update_rows_json_multi(prepared, require_all_matched)

    async def execute_query(
        self, query: str, use_legacy_sql: bool = False, dry_run: bool = False, **kwargs
    ) -> Any:
        return await self.datasource.execute_query(
            query, use_legacy_sql, dry_run, **kwargs
        )

    async def execute_dynamic_query(
        self,
        query: List[Dict[str, Any]],
        rls_filter: Optional[str] = None,
        filter: Optional[str] = None,
        offset: Optional[int] = 0,
        limit: Optional[int] = 100,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        odata_filter, odata_params = self.odata_parser.prepare_odata_filter(filter)
        odata_data_filter, odata_data_params = self.odata_parser.prepare_odata_filter(
            rls_filter
        )
        result_by_query: Dict[str, Any] = await self.datasource.execute_dynamic_query(
            query=query,
            odata_filter=odata_filter,
            odata_params=odata_params,
            odata_data_filter=odata_data_filter,
            odata_data_params=odata_data_params,
            offset=offset,
            limit=limit,
            params=params,
        )
        return result_by_query
