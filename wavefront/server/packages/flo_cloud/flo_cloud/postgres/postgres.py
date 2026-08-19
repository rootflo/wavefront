import re
import string
import logging
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2 import sql

logger = logging.getLogger(__name__)


class NoRowsMatchedError(Exception):
    """An atomic multi-table update had an entry whose filter matched nothing.

    Distinct from a psycopg2 error: the statements were all valid and ran fine,
    but one addressed a row that does not exist. The transaction is rolled back
    before this is raised, so nothing was written.
    """


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
            if self.schema:
                with connection.cursor() as cursor:
                    cursor.execute(
                        sql.SQL('SET search_path TO {}').format(
                            sql.Identifier(self.schema)
                        )
                    )
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

    @staticmethod
    def _qualify_unaliased_columns(clause: str, default_alias: str) -> str:
        """Prefix unqualified column tokens with default_alias to avoid ambiguity in JOINs."""
        if not clause:
            return clause
        _DIRECTION_KEYWORDS = {'ASC', 'DESC', 'NULLS', 'FIRST', 'LAST'}
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
    ) -> str:
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

        # Separate parent (a.*) columns from child columns, mirroring BigQuery's
        # ARRAY_AGG(STRUCT(...)) pattern but using json_agg(json_build_object(...))
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

        order_by_clause = f'ORDER BY {processed_order_by}' if processed_order_by else ''
        base_table = f'{table_prefix}{table_names[0]}'

        if not child_projections:
            # No child columns — plain flat query
            group_by_clause = (
                f'GROUP BY {processed_group_by}' if processed_group_by else ''
            )
            return (
                f'SELECT {projection} FROM {base_table} AS {aliases[0]} '
                f'{processed_join} WHERE {processed_where} '
                f'{group_by_clause} {order_by_clause} '
                f'LIMIT {limit} OFFSET {offset}'
            )

        # Build correlated subqueries for child tables — avoids GROUP BY on parent columns
        join_conditions = {}
        for m in re.finditer(
            r'LEFT JOIN\s+\S+\s+AS\s+(\w+)\s+ON\s+((?:(?!LEFT JOIN).)+)',
            processed_join,
            re.IGNORECASE | re.DOTALL,
        ):
            join_conditions[m.group(1)] = m.group(2).strip()

        subquery_parts = []
        for alias_key, cols in child_projections.items():
            child_idx = aliases.index(alias_key)
            child_table_name = table_names[child_idx]
            full_qualified = f'{table_prefix}{child_table_name}'
            json_args = ', '.join(f"'{name}', {expr}" for name, expr in cols)
            cond = join_conditions.get(alias_key, 'TRUE')
            subquery_parts.append(
                f'(SELECT json_agg(json_build_object({json_args})) '
                f'FROM {full_qualified} AS {alias_key} WHERE {cond}) AS {child_table_name}'
            )

        parent_select = ', '.join(parent_cols) if parent_cols else f'{aliases[0]}.*'
        group_by_clause = f'GROUP BY {processed_group_by}' if processed_group_by else ''
        return (
            f'SELECT {parent_select}, {", ".join(subquery_parts)} '
            f'FROM {base_table} AS {aliases[0]} '
            f'WHERE {processed_where} '
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

    def _build_insert(
        self, table_name: str, data: List[Dict[str, Any]]
    ) -> Tuple[Any, List[Dict[str, Any]]]:
        """Build the parameterized INSERT and the serialized rows for ``data``.

        dict/list column values are wrapped in ``psycopg2.extras.Json``. Assumes
        ``data`` is non-empty (callers guard for that).
        """
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
        return query, serialized

    def insert_rows_json(self, table_name: str, data: List[Dict[str, Any]]) -> None:
        if not data:
            return
        query, serialized = self._build_insert(table_name, data)
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

    def _build_update(
        self,
        table_name: str,
        data: Dict[str, Any],
        where_clause: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, Dict[str, Any]]:
        """Build the parameterized UPDATE and its merged parameters.

        ``data`` maps column to new value, with dict/list values wrapped in
        ``psycopg2.extras.Json`` exactly as ``_build_insert`` does — a jsonb column
        needs it, or the value lands as a quoted text scalar.

        ``where_clause`` is a parameterized predicate (from the OData parser) using
        ``:name`` placeholders, and ``params`` holds its values. Both sides of the
        statement share one parameter dict, so the SET placeholders are prefixed
        ``set_``: the parser names its parameters after the field it filtered on,
        and an unprefixed collision would silently feed one side of the statement
        the other side's value.

        An empty ``where_clause`` is refused. Callers should never construct one —
        this is the last line of defence against an UPDATE that rewrites the whole
        table.
        """
        if not data:
            raise ValueError('No columns to update')
        if not where_clause or not where_clause.strip():
            raise ValueError('A where clause is required to update rows')

        set_params = {
            f'set_{col}': psycopg2.extras.Json(value)
            if isinstance(value, (dict, list))
            else value
            for col, value in data.items()
        }

        # The parser emits ':name'; psycopg2 wants '%(name)s'. Convert the
        # predicate on its own, then compose it in as a trusted SQL fragment.
        converted_where, _ = self._convert_named_params(where_clause, params or {})

        query = sql.SQL('UPDATE {table} SET {assignments} WHERE {where}').format(
            table=sql.Identifier(*table_name.split('.')),
            assignments=sql.SQL(', ').join(
                sql.SQL('{col} = {val}').format(
                    col=sql.Identifier(col), val=sql.Placeholder(name=f'set_{col}')
                )
                for col in data
            ),
            where=sql.SQL(converted_where),
        )

        return query, {**set_params, **(params or {})}

    def update_rows_json(
        self,
        table_name: str,
        data: Dict[str, Any],
        where_clause: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Update the rows matching ``where_clause``, returning how many changed."""
        query, merged_params = self._build_update(
            table_name, data, where_clause, params
        )

        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(query, merged_params)
                updated_rows = cursor.rowcount
                conn.commit()
                return updated_rows
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f'Update error: {e}')
                raise
            finally:
                cursor.close()

    def delete_rows_json(
        self,
        table_name: str,
        where_clause: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Delete the rows matching ``where_clause``, returning how many went.

        ``where_clause`` is a parameterized predicate (from the OData parser) using
        ``:name`` placeholders, with ``params`` holding its values — the same
        contract as ``update_rows_json``, minus the SET side, so there is no
        ``set_`` prefixing to do and the parser's parameters can be used as they
        come.

        An empty ``where_clause`` is refused. A DELETE without a WHERE empties the
        table, and unlike an UPDATE there is no prior value left to reconstruct it
        from, so this check matters more here than anywhere else.
        """
        if not where_clause or not where_clause.strip():
            raise ValueError('A where clause is required to delete rows')

        converted_where, _ = self._convert_named_params(where_clause, params or {})

        query = sql.SQL('DELETE FROM {table} WHERE {where}').format(
            table=sql.Identifier(*table_name.split('.')),
            where=sql.SQL(converted_where),
        )

        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # `or None`, not `or {}`: psycopg2 skips interpolation entirely
                # when params is None, but an empty dict still triggers it and
                # then trips over any literal '%' in a hand-written predicate.
                # Callers coming through the OData parser always bind something,
                # so this only matters to direct users of this class.
                cursor.execute(query, params or None)
                deleted_rows = cursor.rowcount
                conn.commit()
                return deleted_rows
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f'Delete error: {e}')
                raise
            finally:
                cursor.close()

    def update_rows_json_multi(
        self,
        updates: List[Dict[str, Any]],
        require_all_matched: bool = True,
    ) -> List[Dict[str, Any]]:
        """Update rows across multiple tables atomically, in one transaction.

        ``updates`` is a list of
        ``{"table_name": str, "data": Dict, "where_clause": str, "params": Dict}``.
        All tables are written on one connection and committed once; any failure
        rolls back every table (all-or-nothing).

        ``require_all_matched`` is the reason this is not just a loop over
        ``update_rows_json``. The single-table endpoint treats "matched 0 rows" as
        a success, which is right when the caller may not know whether a row
        exists. Here the whole premise is that these rows move *together*, so a
        target that does not exist means the premise is false — committing the
        other half would leave exactly the inconsistency the transaction was meant
        to prevent. Default is therefore to roll back and raise; pass False for
        best-effort semantics.

        Returns one ``{"table_name": str, "updated_rows": int}`` per entry, in
        order.
        """
        if not updates:
            return []

        prepared = [
            (
                spec['table_name'],
                self._build_update(
                    spec['table_name'],
                    spec['data'],
                    spec['where_clause'],
                    spec.get('params'),
                ),
            )
            for spec in updates
        ]

        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                results = []
                for table_name, (query, merged_params) in prepared:
                    cursor.execute(query, merged_params)
                    results.append(
                        {'table_name': table_name, 'updated_rows': cursor.rowcount}
                    )

                if require_all_matched:
                    unmatched = [
                        r['table_name'] for r in results if not r['updated_rows']
                    ]
                    if unmatched:
                        conn.rollback()
                        raise NoRowsMatchedError(
                            'No rows matched the filter for: '
                            f'{", ".join(unmatched)}. Nothing was updated.'
                        )

                conn.commit()
                return results
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f'Multi-update error: {e}')
                raise
            finally:
                cursor.close()

    def insert_rows_json_multi(self, inserts: List[Dict[str, Any]]) -> None:
        """Insert into multiple tables atomically, in a single transaction.

        ``inserts`` is a list of ``{"table_name": str, "data": List[Dict]}``. All
        tables are written on one connection and committed once; any failure rolls
        back every table (all-or-nothing). Entries with empty ``data`` are skipped.
        """
        prepared = [
            self._build_insert(spec['table_name'], spec['data'])
            for spec in inserts
            if spec.get('data')
        ]
        if not prepared:
            return
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                for query, serialized in prepared:
                    cursor.executemany(query, serialized)
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f'Multi-insert error: {e}')
                raise
            finally:
                cursor.close()
