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
    ):
        pass

    @abstractmethod
    async def execute_query(
        self, query: str, use_legacy_sql: bool = False, dry_run: bool = False, **kwargs
    ) -> Any:
        pass
