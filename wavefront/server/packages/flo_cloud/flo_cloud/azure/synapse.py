import os
import re
import string
import logging
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager

import pyodbc

logger = logging.getLogger(__name__)


class SynapseClient:
    """
    Azure Synapse Analytics client using pyodbc.
    Supports both Dedicated SQL Pools and Serverless SQL Pools —
    the pool type is determined by the host URL provided.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: int = 1433,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        driver: str = 'ODBC Driver 18 for SQL Server',
        timeout: int = 30,
    ):
        self.host = host or os.getenv('AZURE_SYNAPSE_HOST')
        self.port = port
        self.database = database or os.getenv('AZURE_SYNAPSE_DATABASE')
        self.user = user or os.getenv('AZURE_SYNAPSE_USER')
        self.password = password or os.getenv('AZURE_SYNAPSE_PASSWORD')
        self.driver = driver
        self.timeout = timeout

        if not self.host:
            raise ValueError(
                'Synapse host must be provided via parameter or AZURE_SYNAPSE_HOST environment variable'
            )
        if not self.database:
            raise ValueError(
                'Database must be provided via parameter or AZURE_SYNAPSE_DATABASE environment variable'
            )
        if not self.user:
            raise ValueError(
                'User must be provided via parameter or AZURE_SYNAPSE_USER environment variable'
            )
        if not self.password:
            raise ValueError(
                'Password must be provided via parameter or AZURE_SYNAPSE_PASSWORD environment variable'
            )

    @staticmethod
    def _escape_conn_value(value: str) -> str:
        """Wrap an ODBC connection-string value in braces, escaping any literal }."""
        return '{' + value.replace('}', '}}') + '}'

    def _build_connection_string(self) -> str:
        return (
            f'DRIVER={self._escape_conn_value(self.driver)};'
            f'Server={self._escape_conn_value(f"{self.host},{self.port}")};'
            f'Database={self._escape_conn_value(self.database)};'
            f'Uid={self._escape_conn_value(self.user)};'
            f'Pwd={self._escape_conn_value(self.password)};'
            f'Encrypt=yes;'
            f'TrustServerCertificate=no;'
            f'Connection Timeout={self.timeout};'
        )

    @contextmanager
    def get_connection(self):
        conn = None
        try:
            conn = pyodbc.connect(self._build_connection_string())
            yield conn
        except pyodbc.Error as e:
            logger.error(f'Synapse connection error: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error connecting to Synapse: {e}')
            raise
        finally:
            if conn:
                conn.close()

    @contextmanager
    def get_cursor(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                yield cursor
            finally:
                cursor.close()

    def _convert_named_params(
        self, query: str, params: Optional[Dict[str, Any]]
    ) -> Tuple[str, list]:
        """Convert @name style named params to ? positional params for pyodbc."""
        if not params:
            return query, []

        ordered_values = []

        def replace_param(match: re.Match) -> str:
            param_name = match.group(1)
            if param_name in params:
                ordered_values.append(params[param_name])
                return '?'
            return match.group(0)

        converted_query = re.sub(r'@(\w+)', replace_param, query)
        return converted_query, ordered_values

    def execute_query_as_dict(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        converted_query, values = self._convert_named_params(query, params)
        with self.get_cursor() as cursor:
            try:
                cursor.execute(converted_query, values)
                columns = [desc[0] for desc in cursor.description]
                seen = set()
                duplicates = {c for c in columns if c in seen or seen.add(c)}
                if duplicates:
                    raise ValueError(
                        f'Duplicate column names {sorted(duplicates)!r} in query result. '
                        f'Query: {converted_query!r}'
                    )
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            except pyodbc.Error as e:
                logger.error(f'Synapse query execution error: {e}')
                raise

    def execute_query_to_dict(
        self,
        projection: str = '*',
        table_prefix: str = '',
        table_names: List[str] = [],
        where_clause: str = '1=1',
        join_query: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        limit: int = 10,
        offset: int = 0,
        order_by: Optional[str] = None,
        group_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not table_names:
            raise ValueError('At least one table name must be provided')

        base_table = f'{table_prefix}{table_names[0]}'
        group_by_clause = f'GROUP BY {group_by}' if group_by else ''
        # SQL Server requires ORDER BY when using OFFSET/FETCH
        order_by_clause = (
            f'ORDER BY {order_by}' if order_by else 'ORDER BY (SELECT NULL)'
        )

        if join_query:
            query = self.__get_join_query(
                join_query,
                table_names,
                table_prefix,
                projection,
                where_clause,
                limit,
                offset,
                order_by,
                group_by=group_by,
            )
        else:
            query = (
                f'SELECT {projection} FROM {base_table} AS a '
                f'WHERE {where_clause} {group_by_clause} '
                f'{order_by_clause} '
                f'OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY'
            )

        try:
            logger.debug(f'Executing query: {query}')
            return self.execute_query_as_dict(query, params)
        except pyodbc.Error as e:
            logger.error(f'Synapse query execution error: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error executing Synapse query: {e}')
            raise

    def __get_join_query(
        self,
        join_query: str,
        table_names: List[str],
        table_prefix: str,
        projection: str,
        where_clause: str,
        limit: int,
        offset: int,
        order_by: Optional[str] = None,
        group_by: Optional[str] = None,
    ) -> str:
        aliases = list(string.ascii_lowercase)
        processed_join = join_query
        processed_where = where_clause
        for i, table_name in enumerate(table_names):
            alias = aliases[i]
            qualified = f'{table_prefix}{table_name}'
            processed_join = processed_join.replace(f'{table_name}.', f'{alias}.')
            processed_where = processed_where.replace(f'{table_name}.', f'{alias}.')
            processed_join = processed_join.replace(
                f'JOIN {table_name}',
                f'JOIN {qualified} AS {alias}',
            )

        group_by_clause = f'GROUP BY {group_by}' if group_by else ''
        order_by_clause = (
            f'ORDER BY {order_by}' if order_by else 'ORDER BY (SELECT NULL)'
        )
        base_table = f'{table_prefix}{table_names[0]}'
        return (
            f'SELECT {projection} FROM {base_table} AS {aliases[0]} '
            f'{processed_join} WHERE {processed_where} '
            f'{group_by_clause} {order_by_clause} '
            f'OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY'
        )

    def get_table_info(self, schema: str = 'dbo') -> List[Dict[str, Any]]:
        query = """
        SELECT
            c.TABLE_NAME,
            c.COLUMN_NAME,
            c.DATA_TYPE,
            c.CHARACTER_MAXIMUM_LENGTH,
            c.NUMERIC_PRECISION,
            c.NUMERIC_SCALE,
            c.IS_NULLABLE,
            c.COLUMN_DEFAULT,
            c.ORDINAL_POSITION
        FROM INFORMATION_SCHEMA.COLUMNS c
        WHERE c.TABLE_SCHEMA = @schema
        ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION
        """
        return self.execute_query_as_dict(query, {'schema': schema})

    def list_tables(self, schema: str = 'dbo') -> List[str]:
        query = (
            'SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES '
            "WHERE TABLE_SCHEMA = ? AND TABLE_TYPE = 'BASE TABLE' "
            'ORDER BY TABLE_NAME'
        )
        with self.get_cursor() as cursor:
            cursor.execute(query, [schema])
            return [row[0] for row in cursor.fetchall()]

    def test_connection(self) -> bool:
        try:
            with self.get_cursor() as cursor:
                cursor.execute('SELECT 1')
                result = cursor.fetchone()
                success = result is not None and result[0] == 1
                if success:
                    logger.info('Synapse connection test successful')
                return success
        except Exception as e:
            logger.error(f'Synapse connection test failed: {e}')
            return False
