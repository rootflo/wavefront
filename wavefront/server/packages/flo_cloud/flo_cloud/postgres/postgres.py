import re
import string
import logging
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Sequence, Tuple
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


@dataclass(frozen=True)
class RowMutationResult:
    """What a row-level UPDATE or DELETE did.

    ``rows_affected`` always comes from ``cursor.rowcount``, which RETURNING does
    not change and which fetching does not consume — so the count stays exact
    however few of the rows are actually pulled into memory.

    ``rows`` is None when the caller did not ask to capture, and [] when it did
    and nothing matched. Those are different facts, and a caller recording an
    audit trail must not conflate them.
    """

    rows_affected: int
    rows: Optional[List[Dict[str, Any]]] = None
    truncated: bool = False
    table_name: Optional[str] = None
    # The predicate's column -> value pairs, as parsed. Filled in a layer up by
    # DatasourcePlugin, which is where an OData filter becomes a where clause;
    # this class only ever receives the compiled form.
    filter_params: Optional[Dict[str, Any]] = None
    # The affected rows as they were *before* an update, read under FOR UPDATE in
    # the same transaction. None when not captured or when the capture failed —
    # distinct from [], which means the capture ran and matched nothing. Updates
    # only: an insert has no prior state, and a delete's `rows` already is one.
    before_rows: Optional[List[Dict[str, Any]]] = None
    # The table's primary key columns, present in both `before_rows` and `rows`
    # so the two can be paired. [] when the table has no primary key, in which
    # case the caller has nothing to pair on.
    key_columns: Optional[List[str]] = None


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

    @contextmanager
    def _write_cursor(self, operation: str = 'Write', dict_rows: bool = False):
        """Yield a cursor on a connection that commits when the block exits.

        The read helpers cannot stand in for this: ``execute_query`` fetches
        results — which a statement without RETURNING does not produce — and
        neither of them commits, so psycopg2 rolls the write back when the
        connection closes. Every writing method therefore needs its own
        connect/execute/commit block, and this is that block in one place.

        ``operation`` only labels the log line, so 'Insert error' and 'Update
        error' stay greppable.

        ``dict_rows`` swaps in RealDictCursor so a RETURNING clause comes back as
        dicts rather than positional tuples — the same mechanism ``get_cursor``
        already uses on the read path. Only the capturing paths need it; the
        plain cursor stays the default so nothing else pays for it.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(**self._cursor_kwargs(dict_rows))
            try:
                yield cursor
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f'{operation} error: {e}')
                raise
            finally:
                cursor.close()

    @staticmethod
    def _cursor_kwargs(dict_rows: bool) -> Dict[str, Any]:
        """Cursor kwargs for a write.

        Returned as a dict rather than passing ``cursor_factory=None`` so that
        the non-capturing path is byte-for-byte the ``conn.cursor()`` call it has
        always been.
        """
        return {'cursor_factory': psycopg2.extras.RealDictCursor} if dict_rows else {}

    @staticmethod
    def _fetch_returned(
        cursor, capture_limit: Optional[int]
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """Pull the RETURNING rows, and say whether more were left behind.

        ``capture_limit`` of None takes everything. With a limit set, one extra
        row is fetched rather than trusting rowcount for the truncation
        decision: the extra row is direct evidence, costs one row, and is
        discarded.

        RealDictRow is a dict subclass, but the rows are copied into plain dicts
        so that nothing downstream — json, a JSONB adapter — has to care.
        """
        if capture_limit is None:
            return [dict(row) for row in cursor.fetchall()], False

        fetched = cursor.fetchmany(capture_limit + 1)
        truncated = len(fetched) > capture_limit
        return [dict(row) for row in fetched[:capture_limit]], truncated

    @staticmethod
    def _primary_key_columns(cursor, table_name: str) -> List[str]:
        """The table's primary key columns, in key order. [] if it has none.

        ``::regclass`` resolves a bare or schema-qualified name against the
        current search_path, which is the same resolution the statements around
        it get.
        """
        cursor.execute(
            'SELECT a.attname AS attname '
            'FROM pg_index i '
            'JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord) '
            '  ON true '
            'JOIN pg_attribute a '
            '  ON a.attrelid = i.indrelid AND a.attnum = k.attnum '
            'WHERE i.indrelid = %(table)s::regclass AND i.indisprimary '
            'ORDER BY k.ord',
            {'table': table_name},
        )
        return [row['attname'] for row in cursor.fetchall()]

    def _capture_before(
        self,
        cursor,
        table_name: str,
        columns: List[str],
        where_clause: str,
        params: Optional[Dict[str, Any]],
        capture_limit: Optional[int],
    ) -> Tuple[Optional[List[Dict[str, Any]]], List[str]]:
        """Read the rows an UPDATE is about to change, before it changes them.

        Postgres cannot return OLD values from a plain ``UPDATE ... RETURNING``
        before v18, so the prior state has to be read separately. Running it on
        the caller's cursor — same connection, same transaction — with FOR UPDATE
        is what makes that safe: the matched rows are locked, so nothing can
        modify them between this read and the UPDATE that follows.

        The whole thing sits inside a savepoint. A failed statement aborts the
        entire Postgres transaction, so without one a pre-read that errors (a
        view, a lock timeout, a missing SELECT grant) would take the caller's
        UPDATE down with it — turning a working mutation into a 500 for the sake
        of an audit detail. On failure this rolls back to the savepoint and
        returns None, and the update proceeds exactly as it would have.

        Returns ``(before_rows, key_columns)``.
        """
        cursor.execute('SAVEPOINT audit_before')
        try:
            key_columns = self._primary_key_columns(cursor, table_name)
            # The key travels with the values so the caller can pair these rows
            # against the post-update ones; without it a multi-row update has no
            # way to tell which before belongs to which after.
            projection = [*key_columns, *(c for c in columns if c not in key_columns)]

            converted_where, _ = self._convert_named_params(where_clause, params or {})

            query = sql.SQL('SELECT {cols} FROM {table} WHERE {where}').format(
                cols=sql.SQL(', ').join(sql.Identifier(c) for c in projection),
                table=sql.Identifier(*table_name.split('.')),
                where=sql.SQL(converted_where),
            )
            if key_columns:
                # Two jobs: it makes a capped subset deterministic rather than
                # whichever rows the scan happened to reach first, and it gives
                # concurrent updates a consistent lock order, which is what stops
                # FOR UPDATE from introducing deadlocks between requests whose
                # filters overlap.
                query = query + sql.SQL(' ORDER BY {cols}').format(
                    cols=sql.SQL(', ').join(sql.Identifier(c) for c in key_columns)
                )
            if capture_limit is not None:
                query = query + sql.SQL(' LIMIT {n}').format(
                    n=sql.Literal(capture_limit)
                )
            # Last, after ORDER BY and LIMIT, so only the returned rows are
            # locked rather than everything the predicate matched.
            query = query + sql.SQL(' FOR UPDATE')

            cursor.execute(query, params or None)
            before_rows = [dict(row) for row in cursor.fetchall()]
            cursor.execute('RELEASE SAVEPOINT audit_before')
            return before_rows, key_columns
        except Exception as e:
            # Deliberately every exception, not just psycopg2.Error. The promise
            # this method makes is that capturing a diff cannot break the
            # mutation, and a TypeError from an unexpected row shape would break
            # it just as thoroughly as a failed statement would.
            #
            # Warning, not error: the mutation is unaffected and about to
            # succeed. Only the diff is lost.
            logger.warning(f'Audit before-capture failed for {table_name}: {e}')
            try:
                cursor.execute('ROLLBACK TO SAVEPOINT audit_before')
            except psycopg2.Error:
                # The connection itself is gone. Nothing left to salvage here —
                # let the UPDATE below surface it as the real failure.
                logger.warning('Could not roll back to the audit savepoint')
            return None, []

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
        with self._write_cursor('Insert') as cursor:
            cursor.executemany(query, serialized)

    @staticmethod
    def _validate_update(data: Dict[str, Any], where_clause: str) -> None:
        """Refuse an UPDATE that cannot be safely built.

        Split out of ``_build_update`` so callers can run it *before* opening a
        connection: the statement can only be built once the primary key is
        known, and that lookup needs a cursor, so without this a malformed
        request would connect just to raise.

        An empty ``where_clause`` is the one that matters — it is the last line
        of defence against an UPDATE that rewrites the whole table.
        """
        if not data:
            raise ValueError('No columns to update')
        if not where_clause or not where_clause.strip():
            raise ValueError('A where clause is required to update rows')

    def _build_update(
        self,
        table_name: str,
        data: Dict[str, Any],
        where_clause: str,
        params: Optional[Dict[str, Any]] = None,
        returning_columns: Optional[Sequence[str]] = None,
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

        ``returning_columns`` appends a RETURNING clause naming exactly those
        columns, so the statement hands back the rows it updated instead of only
        a count. It is the same single statement either way — no extra round
        trip, and nothing to race against. None omits the clause entirely.

        Callers name the columns rather than using ``*``. Only the SET columns
        can have changed, and a wide table makes the difference stark: returning
        ``*`` to record a single integer would carry back — and store — every
        jsonb blob on the row alongside it. A trigger that rewrites one of these
        values still shows up, because the value comes from the row rather than
        from the caller's input. Capturing callers also pass the primary key, so
        the rows can be paired against a pre-update read.

        An empty ``where_clause`` is refused. Callers should never construct one —
        this is the last line of defence against an UPDATE that rewrites the whole
        table.
        """
        self._validate_update(data, where_clause)

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

        if returning_columns:
            query = query + sql.SQL(' RETURNING {columns}').format(
                columns=sql.SQL(', ').join(
                    sql.Identifier(col) for col in returning_columns
                )
            )

        return query, {**set_params, **(params or {})}

    def update_rows_json(
        self,
        table_name: str,
        data: Dict[str, Any],
        where_clause: str,
        params: Optional[Dict[str, Any]] = None,
        capture: bool = False,
        capture_limit: Optional[int] = None,
    ) -> RowMutationResult:
        """Update the rows matching ``where_clause``.

        ``capture`` opts into RETURNING, putting the updated rows on the result —
        restricted to the columns in ``data``, which are the only ones this
        statement can have changed. It also reads those columns' prior values
        first, so the result carries a before as well as an after. Left False —
        the default — the statement issued is exactly the one this method has
        always issued, ``rows`` is None and no pre-read happens, so a caller that
        only wants the count pays for none of it. ``capture_limit`` bounds how
        many rows are materialized on both sides; None takes all of them.
        """
        # Ahead of the connection: the statement cannot be built until the
        # primary key is known, and that needs a cursor.
        self._validate_update(data, where_clause)

        with self._write_cursor('Update', dict_rows=capture) as cursor:
            before_rows: Optional[List[Dict[str, Any]]] = None
            key_columns: List[str] = []
            if capture:
                before_rows, key_columns = self._capture_before(
                    cursor, table_name, list(data), where_clause, params, capture_limit
                )

            returning_columns = (
                [*key_columns, *(c for c in data if c not in key_columns)]
                if capture
                else None
            )
            query, merged_params = self._build_update(
                table_name,
                data,
                where_clause,
                params,
                returning_columns=returning_columns,
            )

            cursor.execute(query, merged_params)
            rows_affected = cursor.rowcount
            if not capture:
                return RowMutationResult(rows_affected=rows_affected)
            rows, truncated = self._fetch_returned(cursor, capture_limit)
            return RowMutationResult(
                rows_affected,
                rows,
                truncated,
                table_name,
                before_rows=before_rows,
                key_columns=key_columns,
            )

    def delete_rows_json(
        self,
        table_name: str,
        where_clause: str,
        params: Optional[Dict[str, Any]] = None,
        capture: bool = False,
        capture_limit: Optional[int] = None,
    ) -> RowMutationResult:
        """Delete the rows matching ``where_clause``, returning how many went.

        ``where_clause`` is a parameterized predicate (from the OData parser) using
        ``:name`` placeholders, with ``params`` holding its values — the same
        contract as ``update_rows_json``, minus the SET side, so there is no
        ``set_`` prefixing to do and the parser's parameters can be used as they
        come.

        ``capture`` opts into RETURNING, putting the deleted rows on the result.
        It matters more here than on the update: after this commits those rows do
        not exist anywhere else, so a caller that wants a record of them has no
        second chance to read them.

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

        if capture:
            query = query + sql.SQL(' RETURNING *')

        with self._write_cursor('Delete', dict_rows=capture) as cursor:
            # `or None`, not `or {}`: psycopg2 skips interpolation entirely when
            # params is None, but an empty dict still triggers it and then trips
            # over any literal '%' in a hand-written predicate. Callers coming
            # through the OData parser always bind something, so this only
            # matters to direct users of this class.
            cursor.execute(query, params or None)
            rows_affected = cursor.rowcount
            if not capture:
                return RowMutationResult(rows_affected=rows_affected)
            rows, truncated = self._fetch_returned(cursor, capture_limit)
            return RowMutationResult(rows_affected, rows, truncated, table_name)

    def update_rows_json_multi(
        self,
        updates: List[Dict[str, Any]],
        require_all_matched: bool = True,
        capture: bool = False,
        capture_limit: Optional[int] = None,
    ) -> List[RowMutationResult]:
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

        ``capture`` opts every entry into RETURNING, as on the single-table
        methods.

        Returns one ``RowMutationResult`` per entry, in order.
        """
        if not updates:
            return []

        # Every entry is checked before a single statement runs, so an invalid
        # one cannot leave a partially applied transaction behind. The statements
        # themselves can only be built inside the loop, once each table's primary
        # key is known.
        for spec in updates:
            self._validate_update(spec['data'], spec['where_clause'])

        # Keeps its own connection block rather than using _write_cursor: it has
        # to decide whether to commit *after* inspecting the row counts, and its
        # rollback path raises NoRowsMatchedError, which is an expected 409 rather
        # than a failure worth an error log.
        with self.get_connection() as conn:
            cursor = conn.cursor(**self._cursor_kwargs(capture))
            try:
                results: List[RowMutationResult] = []
                for spec in updates:
                    table_name = spec['table_name']
                    data = spec['data']
                    where_clause = spec['where_clause']
                    params = spec.get('params')

                    before_rows: Optional[List[Dict[str, Any]]] = None
                    key_columns: List[str] = []
                    if capture:
                        before_rows, key_columns = self._capture_before(
                            cursor,
                            table_name,
                            list(data),
                            where_clause,
                            params,
                            capture_limit,
                        )

                    returning_columns = (
                        [*key_columns, *(c for c in data if c not in key_columns)]
                        if capture
                        else None
                    )
                    query, merged_params = self._build_update(
                        table_name,
                        data,
                        where_clause,
                        params,
                        returning_columns=returning_columns,
                    )

                    cursor.execute(query, merged_params)
                    rows_affected = cursor.rowcount
                    if not capture:
                        results.append(
                            RowMutationResult(
                                rows_affected=rows_affected, table_name=table_name
                            )
                        )
                        continue
                    # Drained before the next execute: a cursor holds only the
                    # most recent result set, so deferring this would lose every
                    # entry but the last.
                    rows, truncated = self._fetch_returned(cursor, capture_limit)
                    results.append(
                        RowMutationResult(
                            rows_affected,
                            rows,
                            truncated,
                            table_name,
                            before_rows=before_rows,
                            key_columns=key_columns,
                        )
                    )

                if require_all_matched:
                    unmatched = [r.table_name for r in results if not r.rows_affected]
                    if unmatched:
                        conn.rollback()
                        # Any rows captured above are discarded along with the
                        # transaction, deliberately: nothing was committed, so
                        # there is no change for a caller to record.
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
        # One cursor for every table, so the commit at the end of the block is
        # what makes this all-or-nothing.
        with self._write_cursor('Multi-insert') as cursor:
            for query, serialized in prepared:
                cursor.executemany(query, serialized)
