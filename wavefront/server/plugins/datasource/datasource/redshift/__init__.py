from typing import Any, Dict, List, Optional

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
        )
        self.db_name = f'{config.database}.public'

    def test_connection(self) -> bool:
        return self.client.test_connection()

    def get_schema(self) -> dict:
        return self.client.get_table_info()

    def get_table_names(self, **kwargs) -> list[str]:
        return self.client.list_tables()

    def fetch_data(
        self,
        table_name: str,
        projection: Optional[str] = None,
        where_clause: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
        order_by: Optional[str] = None,
        group_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        result = self.client.execute_query_to_dict(
            projection=projection,
            table_name=f'{self.db_name}.{table_name}',
            where_clause=where_clause,
            params=params,
            limit=limit,
            offset=offset,
            order_by=order_by,
            group_by=group_by,
        )
        return result

    def insert_rows_json(self, table_name: str, data):
        pass

    def execute_dynamic_query(
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
        # TODO: Implement RLS filter support for Redshift
        # For now, just execute the query without RLS filter
        pass


__all__ = ['RedshiftPlugin', 'RedshiftConfig']
