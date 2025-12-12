import time
import redshift_connector
from functools import wraps
from contextlib import contextmanager
from common_module.log.logger import logger
from flo_utils.legacy_db_repository.legacy_base_db import LegacyBaseDatabase
from typing import List


def retry_on_connection_error(max_retries=3, delay=1, timeout=30):
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            retries = 0
            last_exception = None

            while retries < max_retries:
                try:
                    kwargs.pop('connection', None)
                    with self.get_connection(timeout) as conn:
                        return func(self, *args, **kwargs, connection=conn)
                except (redshift_connector.Error, Exception) as e:
                    last_exception = e
                    retries += 1
                    logger.warning(
                        f'Database connection error: {str(e)}. '
                        f'Attempt {retries} of {max_retries}'
                    )

                    if retries == max_retries:
                        logger.error(
                            f'Max retries reached. Last error: {str(last_exception)}'
                        )
                        raise last_exception

                    time.sleep(delay * retries)  # Exponential backoff
            return None

        return wrapper

    return decorator


class LegacyRedshiftDatastore(LegacyBaseDatabase):
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(LegacyRedshiftDatastore, cls).__new__(cls)
        return cls._instance

    def __init__(
        self,
        redshift_host: str,
        redshift_port: int,
        redshift_db: str,
        redshift_username: str,
        redshift_password: str,
    ):
        self.redshift_host = redshift_host
        self.redshift_port = redshift_port
        self.redshift_db = redshift_db
        self.redshift_username = redshift_username
        self.redshift_password = redshift_password
        if not hasattr(self, 'initialized'):
            super().__init__()
            self._setup_connection_params()
            self.initialized = True

    def _setup_connection_params(self):
        """Setup connection parameters."""
        # Check if we're connecting to a local mock server
        is_local_mock = self.redshift_host in ['localhost', '127.0.0.1']

        self.connection_params = {
            'host': self.redshift_host,
            'port': int(self.redshift_port),
            'database': self.redshift_db,
            'user': self.redshift_username,
            'password': self.redshift_password,
        }

        if is_local_mock:
            self.connection_params['ssl'] = False

    @contextmanager
    def get_connection(self, timeout=30):
        """Context manager for database connections with timeout."""
        connection = None
        try:
            connection = redshift_connector.connect(**self.connection_params)
            yield connection
        except Exception as e:
            logger.error(f'Connection error: {str(e)}')
            raise
        finally:
            if connection:
                connection.close()

    @retry_on_connection_error()
    def execute_query(self, query: str, parameters: dict = None, connection=None):
        """Execute a query with better error handling and logging."""
        try:
            logger.debug(f'Executing query: {query}')
            logger.debug(f'Parameters: {parameters}')

            if connection is None:
                with self.get_connection() as connection:
                    cursor = connection.cursor()
                    if parameters:
                        # Convert named parameters to positional
                        formatted_query = query
                        param_values = []
                        for key, value in parameters.items():
                            formatted_query = formatted_query.replace(f':{key}', '%s')
                            param_values.append(value)
                        cursor.execute(formatted_query, param_values)
                    else:
                        cursor.execute(query)

                    if query.strip().upper().startswith('SELECT'):
                        result = cursor.fetchall()
                    else:
                        connection.commit()
                        result = cursor
                    cursor.close()
            else:
                cursor = connection.cursor()
                if parameters:
                    # Convert named parameters to positional
                    formatted_query = query
                    param_values = []
                    for key, value in parameters.items():
                        formatted_query = formatted_query.replace(f':{key}', '%s')
                        param_values.append(value)
                    cursor.execute(formatted_query, param_values)
                else:
                    cursor.execute(query)

                if query.strip().upper().startswith('SELECT'):
                    result = cursor.fetchall()
                else:
                    result = cursor
                cursor.close()

            if query.strip().upper().startswith('INSERT'):
                logger.info(f'Insert completed. Rowcount: {result.rowcount}')

            return result

        except Exception as e:
            logger.error(
                f'Query execution failed: {str(e)}\n'
                f'Query: {query}\n'
                f'Parameters: {parameters}'
            )
            raise

    def create_tables(self):
        """Create tables using DDL queries from schema manager."""
        table_ddls = self.fetch_ddl_query()
        results = []
        for ddl in table_ddls:
            logger.info(f'Creating table with DDL: {ddl}')
            result = self.execute_query(ddl)
            results.append(result)
        return results

    def _prepare_values_placeholder(self, super_fields: list, column_name: str):
        """Prepare placeholder for field value in SQL"""
        if column_name in super_fields:
            return 'JSON_PARSE(%s)'
        return '%s'

    def bulk_insert_query(self, full_table_name: str, columns) -> str:
        """Generate bulk insert query"""
        BULK_INSERT = f"""
            INSERT INTO {full_table_name} ({', '.join(columns)})
            VALUES ({', '.join([self._prepare_values_placeholder(self.super_fields, col) for col in columns])})
        """
        return BULK_INSERT

    @retry_on_connection_error()
    def bulk_insert(self, full_table_name: str, records: list[dict], connection=None):
        """Improved bulk insert with chunking and progress tracking."""
        if not records:
            logger.warning('No records provided for bulk insert')
            return

        chunk_size = 1000  # Adjust based on your needs
        total_records = len(records)
        columns = records[0].keys()

        logger.info(
            f'Starting bulk insert of {total_records} records into {full_table_name}'
        )

        for i in range(0, total_records, chunk_size):
            chunk = records[i : i + chunk_size]
            bulk_insert_q = self.bulk_insert_query(full_table_name, columns)

            try:
                self.execute_query(bulk_insert_q, chunk, connection=connection)
                logger.info(
                    f'Inserted chunk {i//chunk_size + 1} of '
                    f'{(total_records + chunk_size - 1)//chunk_size}: '
                    f'{len(chunk)} records'
                )
            except Exception as e:
                logger.error(f'Failed to insert chunk {i//chunk_size + 1}: {str(e)}')
                raise

    def fetch_ddl_query(self) -> List[str]:
        """Generate DDL queries for table creation"""
        queries = []

        for table in self.schema['tables']:
            field_definitions = []
            for field_name, field_info in table['fields'].items():
                nullable = 'NULL' if field_info['nullable'] else 'NOT NULL'
                field_definitions.append(
                    f"{field_name} {field_info['type']} {nullable}"
                )

            field_definitions.append('created_at TIMESTAMPTZ NOT NULL')
            fields_sql = ',\n            '.join(field_definitions)

            query = f"""
                CREATE TABLE IF NOT EXISTS {table["name"]} (
                    {fields_sql}
                )
                DISTSTYLE AUTO
                SORTKEY AUTO;
                """
            queries.append(query)
        return queries

    @staticmethod
    def fetch() -> LegacyBaseDatabase:
        """Factory method to get singleton instance."""
        return LegacyRedshiftDatastore()
