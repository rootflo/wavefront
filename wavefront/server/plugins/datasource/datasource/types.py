from enum import Enum
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar, List, Dict, Optional
from dataclasses import dataclass


@dataclass
class Meta:
    status: str
    message: str
    code: int


T = TypeVar('T')


@dataclass
class DataSourceResult(Generic[T]):
    meta: Meta
    result: T


BooleanResult = DataSourceResult[bool]
SchemaResult = DataSourceResult[Dict[str, Any]]
StringResult = DataSourceResult[str]
TableListResult = DataSourceResult[List[str]]
QueryResult = DataSourceResult[List[Dict[str, Any]]]


class DataSourceType(str, Enum):
    AWS_RDS = 'aws_rds'
    AWS_S3 = 'aws_s3'
    AWS_REDSHIFT = 'aws_redshift'
    AZURE_BLOB_STORAGE = 'azure_blob_storage'
    AZURE_DATA_LAKE = 'azure_data_lake'
    AZURE_SQL_DATABASE = 'azure_sql_database'
    AZURE_SQL_DATABASE_V2 = 'azure_sql_database_v2'
    AZURE_SQL_DATA_WAREHOUSE = 'azure_sql_data_warehouse'
    AZURE_SQL_DATA_WAREHOUSE_V2 = 'azure_sql_data_warehouse_v2'
    AZURE_SYNAPSE = 'azure_synapse'
    GCS = 'gcs'
    GCP_BIGQUERY = 'gcp_bigquery'
    MONGODB = 'mongodb'
    MSSQL = 'mssql'
    MYSQL = 'mysql'
    ORACLE = 'oracle'
    POSTGRES = 'postgres'
    REDIS = 'redis'
    SNOWFLAKE = 'snowflake'
    SQLITE = 'sqlite'


class DataSourceABC(ABC):
    @abstractmethod
    async def test_connection(self) -> bool:
        pass

    @abstractmethod
    def get_schema(self) -> dict:
        pass

    @abstractmethod
    def get_table_names(self, **kwargs) -> list[str]:
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def insert_rows_json(self, table_name: str, data: List[Dict[str, Any]]) -> None:
        pass

    def insert_rows_json_multi(self, inserts: List[Dict[str, Any]]) -> None:
        """Insert into multiple tables atomically, in a single transaction.

        ``inserts``: list of ``{"table_name": str, "data": List[Dict]}``. Concrete
        (not abstract) with a NotImplementedError default, so datasource types that
        don't support transactional multi-table insert stay instantiable; plugins
        that do (e.g. Postgres) override this.
        """
        raise NotImplementedError(
            f'{type(self).__name__} does not support transactional multi-table insert'
        )

    def update_rows_json(
        self,
        table_name: str,
        data: Dict[str, Any],
        where_clause: str,
        params: Dict[str, Any],
    ) -> int:
        """Update the rows matching ``where_clause``, returning how many changed.

        ``data`` maps column name to new value; ``where_clause`` is a parameterized
        SQL predicate and ``params`` its values. Concrete (not abstract) with a
        NotImplementedError default, for the same reason as
        ``insert_rows_json_multi``: datasource types that don't support it stay
        instantiable.
        """
        raise NotImplementedError(
            f'{type(self).__name__} does not support updating rows'
        )

    def update_rows_json_multi(
        self, updates: List[Dict[str, Any]], require_all_matched: bool = True
    ) -> List[Dict[str, Any]]:
        """Update rows across multiple tables atomically, in one transaction.

        ``updates``: list of ``{"table_name", "data", "where_clause", "params"}``.
        Concrete with a NotImplementedError default, for the same reason as
        ``insert_rows_json_multi``.
        """
        raise NotImplementedError(
            f'{type(self).__name__} does not support transactional multi-table update'
        )

    def delete_rows_json(
        self,
        table_name: str,
        where_clause: str,
        params: Dict[str, Any],
    ) -> int:
        """Delete the rows matching ``where_clause``, returning how many went.

        ``where_clause`` is a parameterized SQL predicate and ``params`` its
        values. Concrete (not abstract) with a NotImplementedError default, for
        the same reason as ``insert_rows_json_multi``: datasource types that don't
        support it stay instantiable.
        """
        raise NotImplementedError(
            f'{type(self).__name__} does not support deleting rows'
        )

    @abstractmethod
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
        pass

    @abstractmethod
    async def execute_query(
        self, query: str, use_legacy_sql: bool = False, dry_run: bool = False, **kwargs
    ) -> Any:
        pass
