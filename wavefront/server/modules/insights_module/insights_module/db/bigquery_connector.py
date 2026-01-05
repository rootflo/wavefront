from dataclasses import dataclass
import datetime

from common_module.log.logger import logger
from google.cloud import bigquery


@dataclass
class BigQueryConfig:
    project_id: str
    dataset_id: str
    location: str = 'asia-south1'


class BigQueryConnector:
    def __init__(self, bq_config: BigQueryConfig):
        self.config = bq_config
        self.client = self.__get_client()

    def __get_client(self):
        try:
            bq_client = bigquery.Client(
                project=self.config.project_id, location='asia-south1'
            )
            return bq_client
        except Exception as e:
            logger.error(f'Connection error: {str(e)}')
            raise e

    def execute_query(self, query: str, parameters: dict = None):
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

            # Convert RowIterator to list immediately to avoid iterator exhaustion
            rows = list(result)
            column_names = [field.name for field in result.schema]

            if query.strip().upper().startswith('INSERT'):
                logger.info(
                    f'Insert completed. Affected rows: {query_job.num_dml_affected_rows}'
                )
            return rows, column_names

        except Exception as e:
            logger.error(
                f'Query execution failed: {str(e)}\n'
                f'Query: {query}\n'
                f'Parameters: {parameters}'
            )
            raise e
