import re
import json
import string
import logging
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager

import mssql_python

logger = logging.getLogger(__name__)


class MSSQLClient:
    """Microsoft SQL Server client built on the official ``mssql-python`` driver."""

    def __init__(
        self,
        host: str,
        port: int = 1433,
        database: str = None,
        user: str = None,
        password: str = None,
        schema: str = 'dbo',
        encrypt: bool = True,
        trust_server_certificate: bool = False,
        timeout: int = 60,
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.schema = schema
        self.encrypt = encrypt
        self.trust_server_certificate = trust_server_certificate
        self.timeout = timeout

    def _build_connection_string(self) -> str:
        parts = [
            f'SERVER=tcp:{self.host},{self.port}',
            f'DATABASE={self.database}',
            f'UID={self.user}',
            f'PWD={self.password}',
            f'Encrypt={"yes" if self.encrypt else "no"}',
            f'TrustServerCertificate={"yes" if self.trust_server_certificate else "no"}',
        ]
        return ';'.join(parts) + ';'

    def _convert_named_params(
        self, query: str, params: Optional[Dict[str, Any]]
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Convert :name style placeholders to %(name)s for mssql-python (pyformat)."""
        if not params:
            return query, params
        converted = re.sub(r'(?<!:):([A-Za-z_][A-Za-z0-9_]*)', r'%(\1)s', query)
        return converted, params

    @contextmanager
    def get_connection(self):
        connection = None
        try:
            connection = mssql_python.connect(self._build_connection_string())
            yield connection
        except Exception as e:
            logger.error(f'MSSQL connection error: {e}')
            raise
        finally:
            if connection:
                connection.close()

    @contextmanager
    def get_cursor(self, connection=None):
        if connection:
            cursor = connection.cursor()
            try:
                yield cursor
            finally:
                cursor.close()
        else:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                try:
                    yield cursor
                finally:
                    cursor.close()

    @staticmethod
    def _maybe_parse_json(value: Any) -> Any:
        """Best-effort JSON parse for string values that look like a JSON
        object/array. MSSQL has no native JSON type — JSON is stored as plain
        NVARCHAR text — so this is the only signal available to tell JSON
        strings apart from ordinary text without extra schema/config."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped[:1] in ('{', '['):
                try:
                    return json.loads(stripped)
                except (ValueError, TypeError):
                    return value
        return value

    @staticmethod
    def _rows_as_dicts(cursor) -> List[Dict[str, Any]]:
        # DML statements (INSERT/UPDATE/DELETE) produce no result set, so
        # cursor.description is None — return an empty list instead of raising.
        if not cursor.description:
            return []
        columns = [desc[0] for desc in cursor.description]
        return [
            {
                col: MSSQLClient._maybe_parse_json(value)
                for col, value in zip(columns, row)
            }
            for row in cursor.fetchall()
        ]

    def execute_query(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Tuple]:
        query, params = self._convert_named_params(query, params)
        with self.get_cursor() as cursor:
            try:
                cursor.execute(query, params) if params else cursor.execute(query)
                return cursor.fetchall()
            except Exception as e:
                logger.error(f'Query execution error: {e}')
                raise

    def execute_query_as_dict(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        query, params = self._convert_named_params(query, params)
        with self.get_cursor() as cursor:
            try:
                cursor.execute(query, params) if params else cursor.execute(query)
                return self._rows_as_dicts(cursor)
            except Exception as e:
                logger.error(f'Query execution error: {e}')
                raise

    def execute_query_to_dict(
        self,
        projection: str = '*',
        table_prefix: str = '',
        table_names: Optional[List[str]] = None,
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
        child_columns: List[str] = []

        if join_query:
            query, child_columns = self.__get_join_query(
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
            group_by_clause = f'GROUP BY {group_by}' if group_by else ''
            order_by_clause = (
                f'ORDER BY {order_by}' if order_by else 'ORDER BY (SELECT NULL)'
            )
            query = (
                f'SELECT {projection} FROM {base_table} AS a '
                f'WHERE {where_clause} {group_by_clause} {order_by_clause} '
                f'OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY'
            )

        query, params = self._convert_named_params(query, params)
        try:
            logger.debug(f'Executing query: {query}')
            with self.get_cursor() as cursor:
                cursor.execute(query, params) if params else cursor.execute(query)
                rows = self._rows_as_dicts(cursor)
                return self._parse_json_columns(rows, child_columns)
        except Exception as e:
            logger.error(f'MSSQL query execution error: {e}')
            raise

    @staticmethod
    def _parse_json_columns(
        rows: List[Dict[str, Any]], json_columns: List[str]
    ) -> List[Dict[str, Any]]:
        """Parse FOR JSON PATH child columns (returned as strings) into objects."""
        if not json_columns:
            return rows
        for row in rows:
            for col in json_columns:
                value = row.get(col)
                if isinstance(value, str):
                    try:
                        row[col] = json.loads(value)
                    except (ValueError, TypeError):
                        pass
        return rows

    @staticmethod
    def _qualify_unaliased_columns(clause: str, default_alias: str) -> str:
        """Prefix unqualified column tokens with default_alias to avoid ambiguity in JOINs."""
        if not clause:
            return clause
        _DIRECTION_KEYWORDS = {'ASC', 'DESC'}
        parts = clause.split(',')
        result = []
        for part in parts:
            tokens = part.strip().split()
            new_tokens = []
            for token in tokens:
                if token.upper() in _DIRECTION_KEYWORDS:
                    new_tokens.append(token)
                elif '.' not in token and re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', token):
                    new_tokens.append(f'{default_alias}.{token}')
                else:
                    new_tokens.append(token)
            result.append(' '.join(new_tokens))
        return ', '.join(result)

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
    ) -> Tuple[str, List[str]]:
        aliases = list(string.ascii_lowercase)
        processed_join = join_query
        processed_where = where_clause
        processed_order_by = order_by or ''
        processed_group_by = group_by or ''
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
            processed_order_by = re.sub(
                rf'\b{escaped}\.', f'{alias}.', processed_order_by
            )
            processed_group_by = re.sub(
                rf'\b{escaped}\.', f'{alias}.', processed_group_by
            )

        processed_order_by = self._qualify_unaliased_columns(
            processed_order_by, aliases[0]
        )
        processed_group_by = self._qualify_unaliased_columns(
            processed_group_by, aliases[0]
        )

        # Separate parent (a.*) columns from child columns, mirroring the Postgres
        # json_agg(json_build_object(...)) pattern but using FOR JSON PATH.
        parent_cols = []
        child_projections: Dict[
            str, List[tuple]
        ] = {}  # alias -> [(col_name, col_expr)]

        for col in projection.split(','):
            col = col.strip()
            if not col or col == '*':
                continue
            if '.' in col:
                tbl_alias, col_name = col.split('.', 1)
                if tbl_alias == aliases[0]:
                    parent_cols.append(col)
                else:
                    child_projections.setdefault(tbl_alias, []).append((col_name, col))
            else:
                parent_cols.append(col)

        order_by_clause = (
            f'ORDER BY {processed_order_by}'
            if processed_order_by
            else 'ORDER BY (SELECT NULL)'
        )
        base_table = f'{table_prefix}{table_names[0]}'

        if not child_projections:
            # No child columns — plain flat query
            group_by_clause = (
                f'GROUP BY {processed_group_by}' if processed_group_by else ''
            )
            query = (
                f'SELECT {projection} FROM {base_table} AS {aliases[0]} '
                f'{processed_join} WHERE {processed_where} '
                f'{group_by_clause} {order_by_clause} '
                f'OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY'
            )
            return query, []

        # Build correlated subqueries for child tables — avoids GROUP BY on parent columns
        join_conditions = {}
        for m in re.finditer(
            r'LEFT JOIN\s+\S+\s+AS\s+(\w+)\s+ON\s+((?:(?!LEFT JOIN).)+)',
            processed_join,
            re.IGNORECASE | re.DOTALL,
        ):
            join_conditions[m.group(1)] = m.group(2).strip()

        subquery_parts = []
        child_columns = []
        for alias_key, cols in child_projections.items():
            child_idx = aliases.index(alias_key)
            child_table_name = table_names[child_idx]
            full_qualified = f'{table_prefix}{child_table_name}'
            json_select = ', '.join(f'{expr} AS [{name}]' for name, expr in cols)
            cond = join_conditions.get(alias_key, '1=1')
            subquery_parts.append(
                f'(SELECT {json_select} '
                f'FROM {full_qualified} AS {alias_key} WHERE {cond} '
                f'FOR JSON PATH) AS {child_table_name}'
            )
            child_columns.append(child_table_name)

        parent_select = ', '.join(parent_cols) if parent_cols else f'{aliases[0]}.*'
        group_by_clause = f'GROUP BY {processed_group_by}' if processed_group_by else ''
        query = (
            f'SELECT {parent_select}, {", ".join(subquery_parts)} '
            f'FROM {base_table} AS {aliases[0]} '
            f'WHERE {processed_where} '
            f'{group_by_clause} {order_by_clause} '
            f'OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY'
        )
        return query, child_columns

    def list_tables(self, schema: Optional[str] = None) -> List[str]:
        schema = schema or self.schema
        query = """
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = :table_schema AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
        """
        results = self.execute_query(query, {'table_schema': schema})
        return [row[0] for row in results]

    def get_table_info(self, table_name: str) -> Dict[str, Any]:
        query = """
        SELECT
            COLUMN_NAME AS column_name,
            DATA_TYPE AS data_type,
            CHARACTER_MAXIMUM_LENGTH AS character_maximum_length,
            NUMERIC_PRECISION AS numeric_precision,
            NUMERIC_SCALE AS numeric_scale,
            IS_NULLABLE AS is_nullable,
            COLUMN_DEFAULT AS column_default,
            ORDINAL_POSITION AS ordinal_position
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = :table_name AND TABLE_SCHEMA = :table_schema
        ORDER BY ORDINAL_POSITION
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
                logger.info('MSSQL connection test successful')
            return success
        except Exception as e:
            logger.error(f'MSSQL connection test failed: {e}')
            return False

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        """Bracket-quote a SQL Server identifier, escaping any ``]`` by doubling
        it — the only character that can break out of a ``[...]`` context."""
        return '[' + identifier.replace(']', ']]') + ']'

    def insert_rows_json(self, table_name: str, data: List[Dict[str, Any]]) -> None:
        if not data:
            return
        # MSSQL has no native JSON type; JSON values live in NVARCHAR(MAX) columns,
        # so dict/list values are serialized to JSON strings before insert.
        serialized = [
            {
                k: json.dumps(v) if isinstance(v, (dict, list)) else v
                for k, v in row.items()
            }
            for row in data
        ]
        columns = list(serialized[0].keys())
        # MSSQL has no session search_path, so an unqualified table name resolves
        # to the connection's default schema. Qualify it with the configured schema
        # to match the Postgres behavior of honoring self.schema.
        if '.' not in table_name and self.schema:
            table_name = f'{self.schema}.{table_name}'
        quoted_table = '.'.join(
            self._quote_identifier(part) for part in table_name.split('.')
        )
        quoted_cols = ', '.join(self._quote_identifier(col) for col in columns)
        placeholders = ', '.join(f'%({col})s' for col in columns)
        query = f'INSERT INTO {quoted_table} ({quoted_cols}) VALUES ({placeholders})'
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.executemany(query, serialized)
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f'Insert error: {e}')
                raise
            finally:
                cursor.close()
