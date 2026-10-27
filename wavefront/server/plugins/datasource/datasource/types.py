import re
from enum import Enum
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar, List, Dict, Optional
from dataclasses import dataclass

from flo_cloud.postgres import RowMutationResult

# Safe SQL identifiers only (optionally schema-qualified). Table names are
# interpolated into read queries, so reject anything outside this shape.
_TABLE_NAME_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?')
_TABLE_NAME_MAX_LEN = 512


class InvalidResourceError(ValueError):
    """A caller-supplied table name this datasource refuses to query."""


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


FILE_STORAGE_TYPES: frozenset[DataSourceType] = frozenset(
    {
        DataSourceType.AWS_S3,
        DataSourceType.GCS,
        DataSourceType.AZURE_BLOB_STORAGE,
    }
)


def is_file_storage_type(datasource_type: str | DataSourceType | None) -> bool:
    """True for object-storage datasources (upload/download), not SQL ones."""
    try:
        return DataSourceType(datasource_type) in FILE_STORAGE_TYPES
    except ValueError:
        return False


class FileStorageABC(ABC):
    @abstractmethod
    async def test_connection(self) -> bool:
        pass

    @abstractmethod
    def upload_file(
        self, file_content: bytes, path: str, content_type: Optional[str] = None
    ) -> str:
        """Store ``file_content`` at ``path``; return its full URI."""
        pass

    @abstractmethod
    def download_file(self, path: str) -> bytes:
        """Return the bytes at ``path`` (a full URI or a key)."""
        pass


class DataSourceABC(ABC):
    @abstractmethod
    async def test_connection(self) -> bool:
        pass

    def validate_table_name(self, table_name: str) -> None:
        """Raise InvalidResourceError unless ``table_name`` is safe to query.

        The default accepts plain or schema-qualified identifiers. Datasources
        whose naming rules differ override this.
        """
        if (
            not table_name
            or len(table_name) > _TABLE_NAME_MAX_LEN
            or not _TABLE_NAME_RE.fullmatch(table_name)
        ):
            raise InvalidResourceError(f'Invalid resource name: {table_name}')

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
        capture: bool = False,
        capture_limit: Optional[int] = None,
    ) -> RowMutationResult:
        """Update the rows matching ``where_clause``.

        ``data`` maps column name to new value; ``where_clause`` is a parameterized
        SQL predicate and ``params`` its values. ``capture`` asks for the updated
        rows themselves rather than only a count. Concrete (not abstract) with a
        NotImplementedError default, for the same reason as
        ``insert_rows_json_multi``: datasource types that don't support it stay
        instantiable.
        """
        raise NotImplementedError(
            f'{type(self).__name__} does not support updating rows'
        )

    def update_rows_json_multi(
        self,
        updates: List[Dict[str, Any]],
        require_all_matched: bool = True,
        capture: bool = False,
        capture_limit: Optional[int] = None,
    ) -> List[RowMutationResult]:
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
        capture: bool = False,
        capture_limit: Optional[int] = None,
    ) -> RowMutationResult:
        """Delete the rows matching ``where_clause``.

        ``where_clause`` is a parameterized SQL predicate and ``params`` its
        values. ``capture`` asks for the deleted rows themselves — after this
        commits they exist nowhere else. Concrete (not abstract) with a
        NotImplementedError default, for the same reason as
        ``insert_rows_json_multi``: datasource types that don't support it stay
        instantiable.
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
