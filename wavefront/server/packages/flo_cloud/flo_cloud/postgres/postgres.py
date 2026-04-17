import re
import string
import logging
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2 import sql

logger = logging.getLogger(__name__)


class PostgresClient:
    def __init__(
        self,
        host: str,
        port: int = 5432,
        database: str = None,
        user: str = None,
        password: str = None,
        schema: str = 'public',
        ssl: bool = False,
        timeout: int = 60,
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.schema = schema
        self.ssl = ssl
        self.timeout = timeout

    def _get_connection_params(self) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            'host': self.host,
            'port': self.port,
            'dbname': self.database,
            'user': self.user,
            'password': self.password,
            'connect_timeout': self.timeout,
        }
        if self.ssl:
            params['sslmode'] = 'require'
        return params

    def _convert_named_params(
        self, query: str, params: Optional[Dict[str, Any]]
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Convert :name style placeholders to %(name)s for psycopg2."""
        if not params:
            return query, params
        converted = re.sub(r'(?<!:):([A-Za-z_][A-Za-z0-9_]*)', r'%(\1)s', query)
        return converted, params

    @contextmanager
    def get_connection(self):
        connection = None
        try:
            connection = psycopg2.connect(**self._get_connection_params())
            yield connection
        except psycopg2.Error as e:
            logger.error(f'Postgres connection error: {e}')
            raise
        finally:
            if connection:
                connection.close()

    @contextmanager
    def get_cursor(self, connection=None):
        if connection:
            cursor = connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                yield cursor
            finally:
                cursor.close()
        else:
            with self.get_connection() as conn:
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                try:
                    yield cursor
                finally:
                    cursor.close()

    def execute_query(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Tuple]:
        query, params = self._convert_named_params(query, params)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(query, params)
                return cursor.fetchall()
            except psycopg2.Error as e:
                logger.error(f'Query execution error: {e}')
                raise
            finally:
                cursor.close()

    def execute_query_as_dict(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        query, params = self._convert_named_params(query, params)
        with self.get_cursor() as cursor:
            try:
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
            except psycopg2.Error as e:
                logger.error(f'Query execution error: {e}')
                raise

    def execute_query_to_dict(
        self,
        projection: str = '*',
        table_prefix: str = '',
        table_names: Optional[List[str]] = None,
        where_clause: str = 'true',
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
        order_by_clause = f'ORDER BY {order_by}' if order_by else ''

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
                group_by,
            )
        else:
            query = (
                f'SELECT {projection} FROM {base_table} AS a '
                f'WHERE {where_clause} {group_by_clause} {order_by_clause} '
                f'LIMIT {limit} OFFSET {offset}'
            )

        query, params = self._convert_named_params(query, params)
        try:
            logger.debug(f'Executing query: {query}')
            with self.get_cursor() as cursor:
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except psycopg2.Error as e:
            logger.error(f'Postgres query execution error: {e}')
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
            escaped = re.escape(table_name)
            processed_join = re.sub(
                rf'\bJOIN\s+{escaped}\b',
                f'LEFT JOIN {qualified} AS {alias}',
                processed_join,
            )
            processed_join = re.sub(rf'\b{escaped}\.', f'{alias}.', processed_join)
            processed_where = re.sub(rf'\b{escaped}\.', f'{alias}.', processed_where)

        group_by_clause = f'GROUP BY {group_by}' if group_by else ''
        order_by_clause = f'ORDER BY {order_by}' if order_by else ''
        base_table = f'{table_prefix}{table_names[0]}'
        return (
            f'SELECT {projection} FROM {base_table} AS {aliases[0]} '
            f'{processed_join} WHERE {processed_where} '
            f'{group_by_clause} {order_by_clause} '
            f'LIMIT {limit} OFFSET {offset}'
        )

    def list_tables(self, schema: Optional[str] = None) -> List[str]:
        schema = schema or self.schema
        query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %(table_schema)s AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
        results = self.execute_query(query, {'table_schema': schema})
        return [row[0] for row in results]

    def get_table_info(self, table_name: str) -> Dict[str, Any]:
        query = """
        SELECT
            column_name,
            data_type,
            character_maximum_length,
            numeric_precision,
            numeric_scale,
            is_nullable,
            column_default,
            ordinal_position
        FROM information_schema.columns
        WHERE table_name = %(table_name)s AND table_schema = %(table_schema)s
        ORDER BY ordinal_position
        """
        columns = self.execute_query_as_dict(
            query, {'table_name': table_name, 'table_schema': self.schema}
        )
        return {'table_name': table_name, 'columns': columns}

    def test_connection(self) -> bool:
        try:
            result = self.execute_query('SELECT 1')
            success = len(result) > 0 and result[0][0] == 1
            if success:
                logger.info('Postgres connection test successful')
            return success
        except Exception as e:
            logger.error(f'Postgres connection test failed: {e}')
            return False

    def insert_rows_json(self, table_name: str, data: List[Dict[str, Any]]) -> None:
        if not data:
            return
        serialized = [
            {
                k: psycopg2.extras.Json(v) if isinstance(v, (dict, list)) else v
                for k, v in row.items()
            }
            for row in data
        ]
        columns = list(serialized[0].keys())
        query = sql.SQL('INSERT INTO {table} ({cols}) VALUES ({vals})').format(
            table=sql.Identifier(*table_name.split('.')),
            cols=sql.SQL(', ').join(map(sql.Identifier, columns)),
            vals=sql.SQL(', ').join(sql.Placeholder(name=col) for col in columns),
        )
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.executemany(query, serialized)
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f'Insert error: {e}')
                raise
            finally:
                cursor.close()
