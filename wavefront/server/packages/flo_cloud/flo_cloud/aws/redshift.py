import os
import logging
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager
import redshift_connector
from redshift_connector import Connection, Error as RedshiftError

logger = logging.getLogger(__name__)


class RedshiftClient:
    """
    Comprehensive Redshift client using redshift-connector library.
    Provides all essential database operations for Amazon Redshift.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: int = 5439,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        cluster_identifier: Optional[str] = None,
        iam_profile: Optional[str] = None,
        region: Optional[str] = None,
        ssl: bool = True,
        tcp_keepalive: bool = True,
        timeout: int = 60,
        **kwargs,
    ):
        """
        Initialize Redshift client with connection parameters.

        Args:
            host: Redshift cluster endpoint
            port: Redshift port (default: 5439)
            database: Database name
            user: Username for authentication
            password: Password for authentication
            cluster_identifier: Redshift cluster identifier for IAM auth
            iam_profile: IAM profile name for IAM authentication
            region: AWS region
            ssl: Enable SSL connection (default: True)
            timeout: Connection timeout in seconds
            **kwargs: Additional connection parameters
        """
        self.host = host or os.getenv('REDSHIFT_HOST')
        self.port = port
        self.database = database or os.getenv('REDSHIFT_DATABASE')
        self.user = user or os.getenv('REDSHIFT_USER')
        self.password = password or os.getenv('REDSHIFT_PASSWORD')
        self.cluster_identifier = cluster_identifier or os.getenv(
            'REDSHIFT_CLUSTER_IDENTIFIER'
        )
        self.iam_profile = iam_profile or os.getenv('REDSHIFT_IAM_PROFILE')
        self.region = region or os.getenv('AWS_REGION')
        self.ssl = ssl
        self.timeout = timeout
        self.connection_params = kwargs
        self.tcp_keepalive = tcp_keepalive

        if not self.host:
            raise ValueError(
                'Redshift host must be provided via parameter or REDSHIFT_HOST environment variable'
            )

        if not self.database:
            raise ValueError(
                'Database name must be provided via parameter or REDSHIFT_DATABASE environment variable'
            )

    def _get_connection_params(self) -> Dict[str, Any]:
        """Get connection parameters for redshift-connector."""
        params = {
            'host': self.host,
            'port': self.port,
            'database': self.database,
            'ssl': self.ssl,
            'timeout': self.timeout,
            'tcp_keepalive': self.tcp_keepalive,
            **self.connection_params,
        }

        # Use IAM authentication if cluster_identifier is provided
        if self.cluster_identifier:
            params.update(
                {
                    'cluster_identifier': self.cluster_identifier,
                    'region': self.region,
                    'iam_profile': self.iam_profile,
                }
            )
        else:
            # Use username/password authentication
            if not self.user or not self.password:
                raise ValueError(
                    'Username and password must be provided for non-IAM authentication'
                )
            params.update({'user': self.user, 'password': self.password})

        return params

    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        connection = None
        try:
            redshift_connector.paramstyle = 'named'
            connection = redshift_connector.connect(**self._get_connection_params())
            yield connection
        except RedshiftError as e:
            logger.error(f'Redshift connection error: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error connecting to Redshift: {e}')
            raise
        finally:
            if connection:
                connection.close()

    @contextmanager
    def get_cursor(self, connection: Optional[Connection] = None):
        """Context manager for database cursors."""
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

    def execute_query(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> List[Tuple]:
        """
        Execute a SELECT query and return results.

        Args:
            query: SQL query to execute
            params: Query parameters (optional)

        Returns:
            List of tuples containing query results
        """
        with self.get_cursor() as cursor:
            try:
                cursor.execute(query, params)
                return cursor.fetchall()
            except RedshiftError as e:
                logger.error(f'Query execution error: {e}')
                raise

    def execute_query_to_dict(
        self,
        projection: str = '*',
        table_name: str = '',
        where_clause: str = 'true',
        params: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        offset: int = 0,
        order_by: Optional[str] = None,
        group_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute a SELECT query and return results as dictionaries.

        Args:
            projection: Projection of the query
            table_name: Table name
            where_clause: Where clause of the query
            params: Query parameters (optional)
            limit: Maximum number of rows to return
            offset: Number of rows to skip
        Returns:
            List of dictionaries containing query results
        """
        query = f'SELECT {projection} FROM {table_name} WHERE {where_clause} {group_by} {order_by} LIMIT {limit} OFFSET {offset}'
        with self.get_cursor() as cursor:
            try:
                cursor.execute(query, params)
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            except RedshiftError as e:
                logger.error(f'Query execution error: {e}')
                raise

    def execute_command(
        self, command: str, params: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Execute a non-SELECT command (INSERT, UPDATE, DELETE, DDL).

        Args:
            command: SQL command to execute
            params: Command parameters (optional)

        Returns:
            Number of affected rows
        """
        with self.get_cursor() as cursor:
            try:
                cursor.execute(command, params)
                return cursor.rowcount
            except RedshiftError as e:
                logger.error(f'Command execution error: {e}')
                raise

    def execute_many(self, command: str, params_list: List[Dict[str, Any]]) -> int:
        """
        Execute a command with multiple parameter sets (batch operations).

        Args:
            command: SQL command to execute
            params_list: List of parameter tuples

        Returns:
            Number of affected rows
        """
        with self.get_cursor() as cursor:
            try:
                cursor.executemany(command, params_list)
                return cursor.rowcount
            except RedshiftError as e:
                logger.error(f'Batch execution error: {e}')
                raise

    def execute_transaction(
        self, commands: List[Tuple[str, Optional[Dict[str, Any]]]]
    ) -> bool:
        """
        Execute multiple commands in a transaction.

        Args:
            commands: List of (command, params) tuples

        Returns:
            True if transaction succeeded, False otherwise
        """
        with self.get_connection() as connection:
            cursor = connection.cursor()
            try:
                for command, params in commands:
                    cursor.execute(command, params)
                connection.commit()
                return True
            except RedshiftError as e:
                connection.rollback()
                logger.error(f'Transaction error: {e}')
                raise
            finally:
                cursor.close()

    def copy_from_s3(
        self,
        table_name: str,
        s3_path: str,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None,
        region: Optional[str] = None,
        delimiter: str = ',',
        format_type: str = 'CSV',
        header: bool = True,
        compression: Optional[str] = None,
        **kwargs,
    ) -> int:
        """
        Copy data from S3 to Redshift table.

        Args:
            table_name: Target table name
            s3_path: S3 path (s3://bucket/key)
            aws_access_key_id: AWS access key
            aws_secret_access_key: AWS secret key
            aws_session_token: AWS session token
            region: AWS region
            delimiter: Field delimiter
            format_type: File format (CSV, JSON, etc.)
            header: Whether file has header row
            compression: Compression type (GZIP, BZIP2, etc.)
            **kwargs: Additional COPY command options

        Returns:
            Number of rows copied
        """
        # Build COPY command
        copy_command = f"COPY {table_name} FROM '{s3_path}'"

        # Add credentials
        if aws_access_key_id and aws_secret_access_key:
            copy_command += f" CREDENTIALS 'aws_access_key_id={aws_access_key_id};aws_secret_access_key={aws_secret_access_key}'"
            if aws_session_token:
                copy_command += f';token={aws_session_token}'
        else:
            copy_command += ' IAM_ROLE default'

        # Add format options
        copy_command += f' FORMAT AS {format_type}'
        if delimiter != ',':
            copy_command += f" DELIMITER '{delimiter}'"
        if header:
            copy_command += ' HEADER'
        if compression:
            copy_command += f' COMPUPDATE {compression}'

        # Add additional options
        for key, value in kwargs.items():
            copy_command += f' {key.upper()} {value}'

        return self.execute_command(copy_command)

    def copy_to_s3(
        self,
        query: str,
        s3_path: str,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None,
        delimiter: str = ',',
        format_type: str = 'CSV',
        header: bool = True,
        compression: Optional[str] = None,
        **kwargs,
    ) -> int:
        """
        Copy query results to S3.

        Args:
            query: SQL query to execute
            s3_path: S3 path (s3://bucket/key)
            aws_access_key_id: AWS access key
            aws_secret_access_key: AWS secret key
            aws_session_token: AWS session token
            delimiter: Field delimiter
            format_type: File format (CSV, JSON, etc.)
            header: Whether to include header row
            compression: Compression type (GZIP, BZIP2, etc.)
            **kwargs: Additional UNLOAD command options

        Returns:
            Number of rows unloaded
        """
        # Build UNLOAD command
        unload_command = f"UNLOAD ('{query}') TO '{s3_path}'"

        # Add credentials
        if aws_access_key_id and aws_secret_access_key:
            unload_command += f" CREDENTIALS 'aws_access_key_id={aws_access_key_id};aws_secret_access_key={aws_secret_access_key}'"
            if aws_session_token:
                unload_command += f';token={aws_session_token}'
        else:
            unload_command += ' IAM_ROLE default'

        # Add format options
        unload_command += f' FORMAT AS {format_type}'
        if delimiter != ',':
            unload_command += f" DELIMITER '{delimiter}'"
        if header:
            unload_command += ' HEADER'
        if compression:
            unload_command += f' COMPRESSION {compression}'

        # Add additional options
        for key, value in kwargs.items():
            unload_command += f' {key.upper()} {value}'

        return self.execute_command(unload_command)

    def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """
        Get detailed information about a table.

        Args:
            table_name: Name of the table

        Returns:
            Dictionary containing table information
        """
        query = """
        SELECT
            c.column_name,
            c.data_type,
            c.character_maximum_length,
            c.numeric_precision,
            c.numeric_scale,
            c.is_nullable,
            c.column_default,
            c.ordinal_position
        FROM information_schema.columns c
        WHERE c.table_name = :table_name
        ORDER BY c.ordinal_position
        """

        columns = self.execute_query_to_dict(query, {'table_name': table_name})

        # Get table statistics
        stats_query = """
        SELECT
            schemaname,
            tablename,
            attname,
            n_distinct,
            most_common_vals,
            most_common_freqs
        FROM pg_stats
        WHERE tablename = :tablename
        """

        stats = self.execute_query_to_dict(stats_query, {'tablename': table_name})

        return {'table_name': table_name, 'columns': columns, 'statistics': stats}

    def list_tables(self, schema: str = 'public') -> List[str]:
        """
        List all tables in a schema.

        Args:
            schema: Schema name (default: 'public')

        Returns:
            List of table names
        """
        query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = :table_schema AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """

        results = self.execute_query(query, {'table_schema': schema})
        return [row[0] for row in results]

    def get_table_size(self, table_name: str, schema: str = 'public') -> Dict[str, Any]:
        """
        Get table size information.

        Args:
            table_name: Name of the table
            schema: Schema name (default: 'public')

        Returns:
            Dictionary containing size information
        """
        query = """
        SELECT
            schemaname,
            tablename,
            attname,
            n_distinct,
            most_common_vals,
            most_common_freqs
        FROM pg_stats
        WHERE tablename = :tablename AND schemaname = :schemaname
        """

        results = self.execute_query_to_dict(
            query, {'tablename': table_name, 'schemaname': schema}
        )

        # Get size in bytes
        size_query = """
        SELECT
            pg_size_pretty(pg_total_relation_size(:tablename)) as size_pretty,
            pg_total_relation_size(:tablename) as size_bytes
        """

        size_results = self.execute_query_to_dict(
            size_query,
            {
                'tablename': f'{schema}.{table_name}',
                'schemaname': f'{schema}.{table_name}',
            },
        )

        return {
            'table_name': table_name,
            'schema': schema,
            'statistics': results,
            'size': size_results[0] if size_results else {},
        }

    def analyze_table(self, table_name: str, schema: str = 'public') -> bool:
        """
        Run ANALYZE on a table to update statistics.

        Args:
            table_name: Name of the table
            schema: Schema name (default: 'public')

        Returns:
            True if successful
        """
        command = f'ANALYZE {schema}.{table_name}'
        try:
            self.execute_command(command)
            return True
        except RedshiftError as e:
            logger.error(f'ANALYZE failed for {schema}.{table_name}: {e}')
            return False

    def vacuum_table(
        self, table_name: str, schema: str = 'public', full: bool = False
    ) -> bool:
        """
        Run VACUUM on a table to reclaim storage and sort rows.

        Args:
            table_name: Name of the table
            schema: Schema name (default: 'public')
            full: Whether to run FULL VACUUM

        Returns:
            True if successful
        """
        command = f"VACUUM {'FULL ' if full else ''}{schema}.{table_name}"
        try:
            self.execute_command(command)
            return True
        except RedshiftError as e:
            logger.error(f'VACUUM failed for {schema}.{table_name}: {e}')
            return False

    def get_query_plan(self, query: str) -> List[Dict[str, Any]]:
        """
        Get the execution plan for a query.

        Args:
            query: SQL query to analyze

        Returns:
            List of dictionaries containing execution plan details
        """
        explain_query = f'EXPLAIN {query}'
        results = self.execute_query(explain_query)

        # Parse the explain output
        plan_lines = [row[0] for row in results]
        return [{'plan_line': line} for line in plan_lines]

    def cancel_query(self, query_id: str) -> bool:
        """
        Cancel a running query.

        Args:
            query_id: Query ID to cancel

        Returns:
            True if cancellation was successful
        """
        try:
            self.execute_command(f'CANCEL {query_id}')
            return True
        except RedshiftError as e:
            logger.error(f'Failed to cancel query {query_id}: {e}')
            return False

    def get_active_queries(self) -> List[Dict[str, Any]]:
        """
        Get list of currently active queries.

        Returns:
            List of dictionaries containing active query information
        """
        query = """
        SELECT
            pid,
            usename,
            query,
            state,
            starttime,
            query_start,
            state_change
        FROM pg_stat_activity
        WHERE state != 'idle' AND query NOT LIKE '%pg_stat_activity%'
        ORDER BY starttime DESC
        """

        return self.execute_query_to_dict(query)

    def get_query_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent query history from STL_QUERY table.

        Args:
            limit: Maximum number of queries to return

        Returns:
            List of dictionaries containing query history
        """
        query = """
        SELECT
            query,
            starttime,
            endtime,
            elapsed,
            aborted,
            userid,
            pid
        FROM stl_query
        ORDER BY starttime DESC
        LIMIT :limit
        """

        return self.execute_query_to_dict(query, {'limit': limit})

    def test_connection(self) -> bool:
        """
        Test the database connection.

        Returns:
            True if connection is successful
        """
        try:
            result = self.execute_query('SELECT 1')
            return len(result) > 0 and result[0][0] == 1
        except Exception as e:
            logger.error(f'Connection test failed: {e}')
            return False

    def get_cluster_info(self) -> Dict[str, Any]:
        """
        Get Redshift cluster information.

        Returns:
            Dictionary containing cluster information
        """
        queries = {
            'version': 'SELECT version()',
            'current_database': 'SELECT current_database()',
            'current_user': 'SELECT current_user',
            'current_schema': 'SELECT current_schema()',
            'session_id': 'SELECT session_id()',
            'node_count': 'SELECT COUNT(*) FROM stv_slices',
        }

        info = {}
        for key, query in queries.items():
            try:
                result = self.execute_query(query)
                info[key] = result[0][0] if result else None
            except Exception as e:
                logger.warning(f'Failed to get {key}: {e}')
                info[key] = None

        return info
