import time
import logging
from dataclasses import dataclass
from functools import wraps
from contextlib import contextmanager
import redshift_connector

logger = logging.getLogger('RedshiftToolLogger')
logger.setLevel(logging.INFO)


@dataclass
class RedshiftConfig:
    username: str
    password: str
    host: str
    port: str
    db_name: str
    read_only: bool = False


def retry_on_connection_error(max_retries=3, delay=1, timeout=30):
    def decorator(func):
        @wraps(func)
        def wrapper(self: 'RedshiftConnector', *args, **kwargs):
            retries = 0
            last_exception = None

            while retries < max_retries:
                try:
                    kwargs.pop('connection', None)
                    with self.get_connection(timeout) as conn:
                        return func(self, *args, **kwargs, connection=conn)
                except (
                    redshift_connector.Error,
                    redshift_connector.OperationalError,
                ) as e:
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


class RedshiftConnector:
    def __init__(self, redshift_config: RedshiftConfig):
        self.config = redshift_config

    @contextmanager
    def get_connection(self, timeout=300):
        connection = None
        try:
            connection: redshift_connector.Connection = redshift_connector.connect(
                host=self.config.host,
                port=int(self.config.port),
                database=self.config.db_name,
                user=self.config.username,
                password=self.config.password,
                timeout=timeout,
                ssl=True,
                tcp_keepalive=True,
            )
            redshift_connector.paramstyle = 'named'

            if self.config.read_only:
                logger.debug('Making read only connection to redshfit')
                cursor = connection.cursor()
                cursor.execute('SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY')
                cursor.close()

            yield connection
        except Exception as e:
            logger.error(f'Connection error: {str(e)}')
            raise e
        finally:
            self.__close_connection(connection=connection)

    def __close_connection(self, connection: redshift_connector.Connection):
        try:
            if connection:
                connection.close()
        except Exception as e:
            logger.error(f'Connection closing error: {str(e)}')
            raise e

    @retry_on_connection_error()
    def execute_query(
        self,
        query: str,
        parameters: dict = None,
        connection: redshift_connector.Connection = None,
    ):
        try:
            if self.config.read_only:
                query_upper = query.strip().upper()
                write_operations = (
                    'INSERT',
                    'UPDATE',
                    'DELETE',
                    'CREATE',
                    'DROP',
                    'ALTER',
                    'TRUNCATE',
                )
                if any(query_upper.startswith(op) for op in write_operations):
                    raise ValueError(
                        'Write operations are not allowed in read-only mode'
                    )

            logger.debug(f'Executing query: {query}')
            logger.debug(f'Parameters: {parameters}')

            cursor = connection.cursor()

            redshift_connector.paramstyle = 'named'
            if parameters:
                cursor.execute(query, parameters)
            else:
                cursor.execute(query)

            if query.strip().upper().startswith('INSERT'):
                logger.info(f'Insert completed. Rowcount: {cursor.rowcount}')
                return cursor.rowcount

            try:
                results = cursor.fetchall()
                column_names = [desc[0] for desc in cursor.description]
                return results, column_names
            except redshift_connector.ProgrammingError:
                return cursor.rowcount
            finally:
                cursor.close()

        except Exception as e:
            logger.error(
                f'Query execution failed: {str(e)}\n'
                f'Query: {query}\n'
                f'Parameters: {parameters}'
            )
            raise e
