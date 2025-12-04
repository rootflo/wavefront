import time
import datetime
from typing import List, Any
from functools import wraps

from google.cloud import bigquery
from common_module.log.logger import logger
from flo_utils.legacy_db_repository.legacy_base_db import LegacyBaseDatabase


def retry_on_connection_error(max_retries=3, initial_delay=1.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:  # Don't sleep on last attempt
                        time.sleep(delay)
                        delay *= 1.5  # Exponential backoff
            raise last_exception

        return wrapper

    return decorator


class LegacyBigQueryDatastore(LegacyBaseDatabase):
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(LegacyBigQueryDatastore, cls).__new__(cls)
        return cls._instance

    def __init__(self, project_id: str = None, dataset_id: str = None):
        self.project_id = project_id
        self.dataset_id = dataset_id
        if not hasattr(self, 'initialized'):
            super().__init__(cloud_provider='gcp', schema_file='resources/schema.yaml')
            self._create_client()
            self.initialized = True

    def _create_client(self):
        """Create BigQuery client."""
        self.client = bigquery.Client(project=self.project_id)

    @retry_on_connection_error()
    def execute_query(self, query: str, parameters: dict = None) -> Any:
        """Execute a BigQuery query with optional parameters"""
        try:
            logger.debug(f'Executing query: {query}')
            logger.debug(f'Parameters: {parameters}')

            job_config = bigquery.QueryJobConfig()

            if parameters:
                query_params = []
                for key, value in parameters.items():
                    if isinstance(value, str):
                        query_params.append(
                            bigquery.ScalarQueryParameter(key, 'STRING', value)
                        )
                    elif isinstance(value, int):
                        query_params.append(
                            bigquery.ScalarQueryParameter(key, 'INT64', value)
                        )
                    elif isinstance(value, float):
                        query_params.append(
                            bigquery.ScalarQueryParameter(key, 'FLOAT64', value)
                        )
                    elif isinstance(value, bool):
                        query_params.append(
                            bigquery.ScalarQueryParameter(key, 'BOOL', value)
                        )
                    elif isinstance(value, datetime.datetime):
                        query_params.append(
                            bigquery.ScalarQueryParameter(key, 'TIMESTAMP', value)
                        )
                    else:
                        query_params.append(
                            bigquery.ScalarQueryParameter(key, 'STRING', str(value))
                        )

                job_config.query_parameters = query_params

            query_job = self.client.query(query, job_config=job_config)
            result = query_job.result()

            if query.strip().upper().startswith('INSERT'):
                logger.info(
                    f'Insert completed. Affected rows: {query_job.num_dml_affected_rows}'
                )

            return result

        except Exception as e:
            logger.error(
                f'Query execution failed: {str(e)}\n'
                f'Query: {query}\n'
                f'Parameters: {parameters}'
            )
            raise

    @retry_on_connection_error()
    def create_tables(self):
        """Create tables using DDL queries from schema manager."""
        table_ddls = self.fetch_ddl_query()
        results = []
        for ddl in table_ddls:
            logger.info(f'Creating table with DDL: {ddl}')
            result = self.execute_query(ddl)
            results.append(result)
        return results

    @retry_on_connection_error()
    def bulk_insert(self, table_name, records):
        """Improved bulk insert with chunking and progress tracking."""
        if not records:
            logger.warning('No records provided for bulk insert')
            return

        chunk_size = 1000  # Adjust based on your needs
        total_records = len(records)
        table_id = f'{self.project_id}.{self.dataset_id}.{table_name}'

        logger.info(
            f'Starting bulk insert of {total_records} records into {table_name}'
        )

        for i in range(0, total_records, chunk_size):
            chunk = records[i : i + chunk_size]

            try:
                errors = self.client.insert_rows_json(table_id, chunk)

                if errors:
                    logger.error(f'Errors during bulk insert: {errors}')
                    raise Exception(f'Failed to insert chunk: {errors}')

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
                nullable = '' if field_info['nullable'] else 'NOT NULL'
                bq_type = self._convert_to_bigquery_type(field_info['type'])
                field_definitions.append(f'{field_name} {bq_type} {nullable}')

            field_definitions.append('created_at TIMESTAMP NOT NULL')
            fields_sql = ',\n            '.join(field_definitions)

            full_table_name = f'{self.dataset_id}.{table["name"]}'
            query = f"""
                CREATE TABLE IF NOT EXISTS {full_table_name} (
                    {fields_sql}
                )
                """
            queries.append(query)
        return queries

    def _convert_to_bigquery_type(self, redshift_type: str) -> str:
        """Convert Redshift data types to equivalent BigQuery data types."""
        type_mapping = {
            'INTEGER': 'INT64',
            'INT': 'INT64',
            'SMALLINT': 'INT64',
            'BIGINT': 'INT64',
            'DECIMAL': 'NUMERIC',
            'NUMERIC': 'NUMERIC',
            'REAL': 'FLOAT64',
            'DOUBLE PRECISION': 'FLOAT64',
            'FLOAT': 'FLOAT64',
            'CHAR': 'STRING',
            'CHARACTER': 'STRING',
            'VARCHAR': 'STRING',
            'TEXT': 'STRING',
            'DATE': 'DATE',
            'TIME': 'TIME',
            'TIMETZ': 'TIME',
            'TIMESTAMP': 'TIMESTAMP',
            'TIMESTAMPTZ': 'TIMESTAMP',
            'BOOLEAN': 'BOOL',
            'BOOL': 'BOOL',
            'SUPER': 'JSON',
        }

        base_type = redshift_type.split('(')[0].upper()
        if base_type in type_mapping:
            if '(' in redshift_type and base_type in ['DECIMAL', 'NUMERIC']:
                precision_scale = redshift_type[redshift_type.find('(') :]
                return f'{type_mapping[base_type]}{precision_scale}'
            return type_mapping[base_type]

        return 'STRING'

    @staticmethod
    def fetch(project_id: str, dataset_id: str) -> LegacyBaseDatabase:
        """Factory method to get singleton instance."""
        return LegacyBigQueryDatastore(project_id=project_id, dataset_id=dataset_id)
