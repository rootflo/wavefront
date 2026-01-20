import os
import string
import logging
import asyncio
from google.oauth2 import service_account
from typing import List, Dict, Any, Optional, Union
from datetime import datetime

from google.cloud import bigquery
from google.cloud.bigquery import (
    Dataset,
    Table,
    SchemaField,
    QueryJob,
    LoadJob,
    CopyJob,
    ExtractJob,
    TimePartitioning,
    DestinationFormat,
    SourceFormat,
    WriteDisposition,
    CreateDisposition,
    DatasetReference,
    TableReference,
)
from google.cloud.bigquery.job import (
    QueryJobConfig,
    LoadJobConfig,
    CopyJobConfig,
    ExtractJobConfig,
)
from google.cloud.bigquery.table import TableListItem
from google.cloud.exceptions import GoogleCloudError


logger = logging.getLogger(__name__)


class BigQueryClient:
    """
    Comprehensive BigQuery client using google-cloud-bigquery library.
    Provides all essential operations for Google BigQuery.
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        credentials_path: Optional[str] = None,
        credentials_json: Optional[dict] = None,
        timeout: int = 300,
        **kwargs,
    ):
        """
        Initialize BigQuery client with connection parameters.

        Args:
            project_id: Google Cloud project ID
            location: BigQuery dataset location (e.g., 'US', 'EU', 'asia-northeast1')
            credentials_path: Path to service account JSON file
            credentials_json: Service account JSON string
            timeout: Query timeout in seconds
            **kwargs: Additional client parameters
        """
        self.project_id = project_id or os.getenv('GOOGLE_CLOUD_PROJECT')
        self.location = location or os.getenv('BIGQUERY_LOCATION', 'asia-south1')
        self.timeout = timeout
        self.client_params = kwargs

        if not self.project_id:
            raise ValueError(
                'Project ID must be provided via parameter or GOOGLE_CLOUD_PROJECT environment variable'
            )

        # Initialize credentials
        credentials = None
        if credentials_path:
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path
            )
        elif credentials_json:
            credentials = service_account.Credentials.from_service_account_info(
                credentials_json
            )

        # Initialize BigQuery client
        if credentials:
            self.client = bigquery.Client(
                project=self.project_id, credentials=credentials, **self.client_params
            )
        else:
            # Falls back to default credentials (application default credentials)
            self.client = bigquery.Client(project=self.project_id, **self.client_params)

    def _get_dataset_ref(self, dataset_id: str) -> DatasetReference:
        """Get dataset reference."""
        return DatasetReference(self.project_id, dataset_id)

    def _get_table_ref(self, dataset_id: str, table_id: str) -> TableReference:
        """Get table reference."""
        dataset_ref = self._get_dataset_ref(dataset_id)
        return TableReference(dataset_ref, table_id)

    def _get_query_params(self, params: Optional[dict] = None):
        """Get query parameters."""
        query_params = []
        for key, value in params.items():
            if isinstance(value, str):
                query_params.append(bigquery.ScalarQueryParameter(key, 'STRING', value))
            elif isinstance(value, int):
                query_params.append(bigquery.ScalarQueryParameter(key, 'INT64', value))
            elif isinstance(value, float):
                query_params.append(
                    bigquery.ScalarQueryParameter(key, 'FLOAT64', value)
                )
            elif isinstance(value, bool):
                query_params.append(bigquery.ScalarQueryParameter(key, 'BOOL', value))
            elif isinstance(value, datetime):
                query_params.append(
                    bigquery.ScalarQueryParameter(key, 'TIMESTAMP', value)
                )
            else:
                query_params.append(
                    bigquery.ScalarQueryParameter(key, 'STRING', str(value))
                )
        return query_params

    async def execute_query(
        self,
        query: str,
        use_legacy_sql: bool = False,
        dry_run: bool = False,
        params: Optional[dict] = None,
        **kwargs,
    ) -> QueryJob:
        """
        Execute a BigQuery SQL query.

        Args:
            query: SQL query to execute
            use_legacy_sql: Whether to use legacy SQL (default: False)
            dry_run: Whether to perform a dry run (default: False)
            **kwargs: Additional query configuration parameters

        Returns:
            QueryJob object
        """
        try:
            job_config = QueryJobConfig(
                use_legacy_sql=use_legacy_sql, dry_run=dry_run, **kwargs
            )
            if params:
                job_config.query_parameters = self._get_query_params(params)

            # Run the blocking query operation in a thread pool
            query_job = await asyncio.to_thread(
                self.client.query, query, job_config=job_config
            )

            if not dry_run:
                # Run the blocking result() call in a thread pool
                await asyncio.to_thread(query_job.result, timeout=self.timeout)

            return query_job

        except GoogleCloudError as e:
            logger.error(f'BigQuery query execution error: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error executing BigQuery query: {e}')
            raise

    def execute_query_to_dataframe(
        self, query: str, use_legacy_sql: bool = False, **kwargs
    ):
        """
        Execute a query and return results as a pandas DataFrame.

        Args:
            query: SQL query to execute
            use_legacy_sql: Whether to use legacy SQL
            **kwargs: Additional query configuration parameters

        Returns:
            pandas DataFrame with query results
        """
        try:
            job_config = QueryJobConfig(use_legacy_sql=use_legacy_sql, **kwargs)

            df = self.client.query(query, job_config=job_config).to_dataframe()
            return df

        except ImportError:
            raise ImportError(
                'pandas is required for this method. Install with: pip install pandas'
            )
        except GoogleCloudError as e:
            logger.error(f'BigQuery query execution error: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error executing BigQuery query: {e}')
            raise

    def execute_query_to_dict(
        self,
        projection: str = '*',
        table_prefix: str = '',
        table_names: List[str] = [],
        where_clause: str = 'true',
        join_query: Optional[str] = None,
        params: Optional[dict] = None,
        limit: int = 10,
        offset: int = 0,
        use_legacy_sql: bool = False,
        order_by: Optional[str] = None,
        group_by: Optional[str] = None,
        **kwargs,
    ) -> Union[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Execute a query and return results as a list of dictionaries or structured list for joins.

        Args:
            projection: Projection of the query
            table_prefix: Prefix for table names
            table_names: List of table names
            where_clause: Where clause of the query
            join_query: Join query string (optional)
            params: Query parameters (optional)
            limit: Maximum number of rows to return
            offset: Number of rows to skip
            use_legacy_sql: Whether to use legacy SQL
            **kwargs: Additional query configuration parameters

        Returns:
            If join_query is provided:
                List of dictionaries, each containing main table fields and child table objects
            Otherwise:
                List of dictionaries containing query results
        """

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
            group_by_clause = f'GROUP BY {group_by}' if group_by else ''
            order_by_clause = f'ORDER BY {order_by}' if order_by else ''
            query = f'SELECT {projection} FROM `{table_prefix}{table_names[0]}` AS a WHERE {where_clause} {group_by_clause} {order_by_clause} LIMIT {limit} OFFSET {offset}'

        try:
            job_config = QueryJobConfig(use_legacy_sql=use_legacy_sql, **kwargs)
            if params:
                job_config.query_parameters = self._get_query_params(params)

            logger.debug(f'Executing query: {query}')
            query_job = self.client.query(query, job_config=job_config)
            results = query_job.result(timeout=self.timeout)

            return [dict(row.items()) for row in results]

        except GoogleCloudError as e:
            logger.error(f'BigQuery query execution error: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error executing BigQuery query: {e}')
            raise

    def create_dataset(
        self,
        dataset_id: str,
        description: Optional[str] = None,
        location: Optional[str] = None,
        **kwargs,
    ) -> Dataset:
        """
        Create a new BigQuery dataset.

        Args:
            dataset_id: Dataset ID
            description: Dataset description
            location: Dataset location
            **kwargs: Additional dataset configuration parameters

        Returns:
            Created Dataset object
        """
        try:
            dataset_ref = self._get_dataset_ref(dataset_id)
            dataset = Dataset(dataset_ref)

            if description:
                dataset.description = description
            if location:
                dataset.location = location

            # Set additional properties
            for key, value in kwargs.items():
                if hasattr(dataset, key):
                    setattr(dataset, key, value)

            dataset = self.client.create_dataset(dataset, timeout=self.timeout)
            logger.info(f'Created dataset {dataset_id}')
            return dataset

        except GoogleCloudError as e:
            logger.error(f'Error creating dataset {dataset_id}: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error creating dataset {dataset_id}: {e}')
            raise

    def delete_dataset(
        self, dataset_id: str, delete_contents: bool = False, not_found_ok: bool = False
    ) -> bool:
        """
        Delete a BigQuery dataset.

        Args:
            dataset_id: Dataset ID
            delete_contents: Whether to delete all tables in the dataset
            not_found_ok: Whether to ignore if dataset doesn't exist

        Returns:
            True if dataset was deleted, False otherwise
        """
        try:
            dataset_ref = self._get_dataset_ref(dataset_id)
            self.client.delete_dataset(
                dataset_ref, delete_contents=delete_contents, not_found_ok=not_found_ok
            )
            logger.info(f'Deleted dataset {dataset_id}')
            return True

        except GoogleCloudError as e:
            if not_found_ok and 'Not found' in str(e):
                return False
            logger.error(f'Error deleting dataset {dataset_id}: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error deleting dataset {dataset_id}: {e}')
            raise

    def list_datasets(self, **kwargs) -> List[Dataset]:
        """
        List all datasets in the project.

        Args:
            **kwargs: Additional list parameters

        Returns:
            List of Dataset objects
        """
        try:
            datasets = list(self.client.list_datasets(**kwargs))
            return datasets

        except GoogleCloudError as e:
            logger.error(f'Error listing datasets: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error listing datasets: {e}')
            raise

    def create_table(
        self,
        dataset_id: str,
        table_id: str,
        schema: Optional[List[SchemaField]] = None,
        description: Optional[str] = None,
        time_partitioning: Optional[TimePartitioning] = None,
        clustering_fields: Optional[List[str]] = None,
        **kwargs,
    ) -> Table:
        """
        Create a new BigQuery table.

        Args:
            dataset_id: Dataset ID
            table_id: Table ID
            schema: Table schema (list of SchemaField objects)
            description: Table description
            time_partitioning: Time partitioning configuration
            clustering_fields: List of field names for clustering
            **kwargs: Additional table configuration parameters

        Returns:
            Created Table object
        """
        try:
            table_ref = self._get_table_ref(dataset_id, table_id)
            table = Table(table_ref, schema=schema)

            if description:
                table.description = description
            if time_partitioning:
                table.time_partitioning = time_partitioning
            if clustering_fields:
                table.clustering_fields = clustering_fields

            # Set additional properties
            for key, value in kwargs.items():
                if hasattr(table, key):
                    setattr(table, key, value)

            table = self.client.create_table(table, timeout=self.timeout)
            logger.info(f'Created table {dataset_id}.{table_id}')
            return table

        except GoogleCloudError as e:
            logger.error(f'Error creating table {dataset_id}.{table_id}: {e}')
            raise
        except Exception as e:
            logger.error(
                f'Unexpected error creating table {dataset_id}.{table_id}: {e}'
            )
            raise

    def delete_table(
        self, dataset_id: str, table_id: str, not_found_ok: bool = False
    ) -> bool:
        """
        Delete a BigQuery table.

        Args:
            dataset_id: Dataset ID
            table_id: Table ID
            not_found_ok: Whether to ignore if table doesn't exist

        Returns:
            True if table was deleted, False otherwise
        """
        try:
            table_ref = self._get_table_ref(dataset_id, table_id)
            self.client.delete_table(table_ref, not_found_ok=not_found_ok)
            logger.info(f'Deleted table {dataset_id}.{table_id}')
            return True

        except GoogleCloudError as e:
            if not_found_ok and 'Not found' in str(e):
                return False
            logger.error(f'Error deleting table {dataset_id}.{table_id}: {e}')
            raise
        except Exception as e:
            logger.error(
                f'Unexpected error deleting table {dataset_id}.{table_id}: {e}'
            )
            raise

    def list_tables(self, dataset_id: str, **kwargs) -> List[TableListItem]:
        """
        List all tables in a dataset.

        Args:
            dataset_id: Dataset ID
            **kwargs: Additional list parameters

        Returns:
            List of Table objects
        """
        try:
            dataset_ref = self._get_dataset_ref(dataset_id)
            tables = list(self.client.list_tables(dataset_ref, **kwargs))
            return tables

        except GoogleCloudError as e:
            logger.error(f'Error listing tables in dataset {dataset_id}: {e}')
            raise
        except Exception as e:
            logger.error(
                f'Unexpected error listing tables in dataset {dataset_id}: {e}'
            )
            raise

    def get_table(self, dataset_id: str, table_id: str) -> Table:
        """
        Get a BigQuery table.

        Args:
            dataset_id: Dataset ID
            table_id: Table ID

        Returns:
            Table object
        """
        try:
            table_ref = self._get_table_ref(dataset_id, table_id)
            table = self.client.get_table(table_ref)
            return table

        except GoogleCloudError as e:
            logger.error(f'Error getting table {dataset_id}.{table_id}: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error getting table {dataset_id}.{table_id}: {e}')
            raise

    def update_table(self, dataset_id: str, table_id: str, **kwargs) -> Table:
        """
        Update a BigQuery table.

        Args:
            dataset_id: Dataset ID
            table_id: Table ID
            **kwargs: Table properties to update

        Returns:
            Updated Table object
        """
        try:
            table_ref = self._get_table_ref(dataset_id, table_id)
            table = self.client.get_table(table_ref)

            # Update table properties
            for key, value in kwargs.items():
                if hasattr(table, key):
                    setattr(table, key, value)

            updated_table = self.client.update_table(table, fields=list(kwargs.keys()))
            logger.info(f'Updated table {dataset_id}.{table_id}')
            return updated_table

        except GoogleCloudError as e:
            logger.error(f'Error updating table {dataset_id}.{table_id}: {e}')
            raise
        except Exception as e:
            logger.error(
                f'Unexpected error updating table {dataset_id}.{table_id}: {e}'
            )
            raise

    def load_table_from_dataframe(
        self,
        dataframe,
        dataset_id: str,
        table_id: str,
        write_disposition: WriteDisposition = WriteDisposition.WRITE_APPEND,
        create_disposition: CreateDisposition = CreateDisposition.CREATE_IF_NEEDED,
        schema: Optional[List[SchemaField]] = None,
        **kwargs,
    ) -> LoadJob:
        """
        Load data from a pandas DataFrame into a BigQuery table.

        Args:
            dataframe: pandas DataFrame to load
            dataset_id: Dataset ID
            table_id: Table ID
            write_disposition: Write disposition (WRITE_TRUNCATE, WRITE_APPEND, WRITE_EMPTY)
            create_disposition: Create disposition (CREATE_IF_NEEDED, CREATE_NEVER)
            schema: Table schema (optional)
            **kwargs: Additional load configuration parameters

        Returns:
            LoadJob object
        """
        try:
            table_ref = self._get_table_ref(dataset_id, table_id)

            job_config = LoadJobConfig(
                write_disposition=write_disposition,
                create_disposition=create_disposition,
                schema=schema,
                **kwargs,
            )

            load_job = self.client.load_table_from_dataframe(
                dataframe, table_ref, job_config=job_config
            )
            load_job.result(timeout=self.timeout)

            logger.info(f'Loaded {len(dataframe)} rows into {dataset_id}.{table_id}')
            return load_job

        except ImportError:
            raise ImportError(
                'pandas is required for this method. Install with: pip install pandas'
            )
        except GoogleCloudError as e:
            logger.error(f'Error loading data into {dataset_id}.{table_id}: {e}')
            raise
        except Exception as e:
            logger.error(
                f'Unexpected error loading data into {dataset_id}.{table_id}: {e}'
            )
            raise

    def load_table_from_file(
        self,
        source_file: str,
        dataset_id: str,
        table_id: str,
        source_format: SourceFormat = SourceFormat.CSV,
        write_disposition: WriteDisposition = WriteDisposition.WRITE_APPEND,
        create_disposition: CreateDisposition = CreateDisposition.CREATE_IF_NEEDED,
        schema: Optional[List[SchemaField]] = None,
        **kwargs,
    ) -> LoadJob:
        """
        Load data from a file into a BigQuery table.

        Args:
            source_file: Path to source file
            dataset_id: Dataset ID
            table_id: Table ID
            source_format: Source file format (CSV, JSON, AVRO, PARQUET, etc.)
            write_disposition: Write disposition
            create_disposition: Create disposition
            schema: Table schema (optional)
            **kwargs: Additional load configuration parameters

        Returns:
            LoadJob object
        """
        try:
            table_ref = self._get_table_ref(dataset_id, table_id)

            job_config = LoadJobConfig(
                source_format=source_format,
                write_disposition=write_disposition,
                create_disposition=create_disposition,
                schema=schema,
                **kwargs,
            )

            with open(source_file, 'rb') as source_file_obj:
                load_job = self.client.load_table_from_file(
                    source_file_obj, table_ref, job_config=job_config
                )
                load_job.result(timeout=self.timeout)

            logger.info(f'Loaded data from {source_file} into {dataset_id}.{table_id}')
            return load_job

        except GoogleCloudError as e:
            logger.error(
                f'Error loading data from {source_file} into {dataset_id}.{table_id}: {e}'
            )
            raise
        except Exception as e:
            logger.error(
                f'Unexpected error loading data from {source_file} into {dataset_id}.{table_id}: {e}'
            )
            raise

    def load_table_from_uri(
        self,
        source_uris: Union[str, List[str]],
        dataset_id: str,
        table_id: str,
        source_format: SourceFormat = SourceFormat.CSV,
        write_disposition: WriteDisposition = WriteDisposition.WRITE_APPEND,
        create_disposition: CreateDisposition = CreateDisposition.CREATE_IF_NEEDED,
        schema: Optional[List[SchemaField]] = None,
        **kwargs,
    ) -> LoadJob:
        """
        Load data from Google Cloud Storage URIs into a BigQuery table.

        Args:
            source_uris: GCS URI(s) (gs://bucket/path/to/file)
            dataset_id: Dataset ID
            table_id: Table ID
            source_format: Source file format
            write_disposition: Write disposition
            create_disposition: Create disposition
            schema: Table schema (optional)
            **kwargs: Additional load configuration parameters

        Returns:
            LoadJob object
        """
        try:
            table_ref = self._get_table_ref(dataset_id, table_id)

            job_config = LoadJobConfig(
                source_format=source_format,
                write_disposition=write_disposition,
                create_disposition=create_disposition,
                schema=schema,
                **kwargs,
            )

            load_job = self.client.load_table_from_uri(
                source_uris, table_ref, job_config=job_config
            )
            load_job.result(timeout=self.timeout)

            logger.info(f'Loaded data from {source_uris} into {dataset_id}.{table_id}')
            return load_job

        except GoogleCloudError as e:
            logger.error(
                f'Error loading data from {source_uris} into {dataset_id}.{table_id}: {e}'
            )
            raise
        except Exception as e:
            logger.error(
                f'Unexpected error loading data from {source_uris} into {dataset_id}.{table_id}: {e}'
            )
            raise

    def copy_table(
        self,
        source_dataset_id: str,
        source_table_id: str,
        destination_dataset_id: str,
        destination_table_id: str,
        write_disposition: WriteDisposition = WriteDisposition.WRITE_TRUNCATE,
        create_disposition: CreateDisposition = CreateDisposition.CREATE_IF_NEEDED,
        **kwargs,
    ) -> CopyJob:
        """
        Copy a BigQuery table.

        Args:
            source_dataset_id: Source dataset ID
            source_table_id: Source table ID
            destination_dataset_id: Destination dataset ID
            destination_table_id: Destination table ID
            write_disposition: Write disposition
            create_disposition: Create disposition
            **kwargs: Additional copy configuration parameters

        Returns:
            CopyJob object
        """
        try:
            source_table_ref = self._get_table_ref(source_dataset_id, source_table_id)
            destination_table_ref = self._get_table_ref(
                destination_dataset_id, destination_table_id
            )

            job_config = CopyJobConfig(
                write_disposition=write_disposition,
                create_disposition=create_disposition,
                **kwargs,
            )

            copy_job = self.client.copy_table(
                source_table_ref, destination_table_ref, job_config=job_config
            )
            copy_job.result(timeout=self.timeout)

            logger.info(
                f'Copied table {source_dataset_id}.{source_table_id} to {destination_dataset_id}.{destination_table_id}'
            )
            return copy_job

        except GoogleCloudError as e:
            logger.error(
                f'Error copying table {source_dataset_id}.{source_table_id}: {e}'
            )
            raise
        except Exception as e:
            logger.error(
                f'Unexpected error copying table {source_dataset_id}.{source_table_id}: {e}'
            )
            raise

    def extract_table_to_gcs(
        self,
        dataset_id: str,
        table_id: str,
        destination_uris: Union[str, List[str]],
        destination_format: DestinationFormat = DestinationFormat.CSV,
        **kwargs,
    ) -> ExtractJob:
        """
        Extract a BigQuery table to Google Cloud Storage.

        Args:
            dataset_id: Dataset ID
            table_id: Table ID
            destination_uris: GCS destination URI(s) (gs://bucket/path/to/file)
            destination_format: Destination format (CSV, JSON, AVRO, PARQUET)
            **kwargs: Additional extract configuration parameters

        Returns:
            ExtractJob object
        """
        try:
            table_ref = self._get_table_ref(dataset_id, table_id)

            job_config = ExtractJobConfig(
                destination_format=destination_format, **kwargs
            )

            extract_job = self.client.extract_table(
                table_ref, destination_uris, job_config=job_config
            )
            extract_job.result(timeout=self.timeout)

            logger.info(
                f'Extracted table {dataset_id}.{table_id} to {destination_uris}'
            )
            return extract_job

        except GoogleCloudError as e:
            logger.error(f'Error extracting table {dataset_id}.{table_id}: {e}')
            raise
        except Exception as e:
            logger.error(
                f'Unexpected error extracting table {dataset_id}.{table_id}: {e}'
            )
            raise

    def get_table_info(self, dataset_id: str, table_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a BigQuery table.

        Args:
            dataset_id: Dataset ID
            table_id: Table ID

        Returns:
            Dictionary containing table information
        """
        try:
            table = self.get_table(dataset_id, table_id)

            info = {
                'table_id': table.table_id,
                'dataset_id': table.dataset_id,
                'project': table.project,
                'created': table.created,
                'modified': table.modified,
                'description': table.description,
                'num_rows': table.num_rows,
                'num_bytes': table.num_bytes,
                'schema': [field.to_api_repr() for field in table.schema]
                if table.schema
                else [],
                'time_partitioning': table.time_partitioning.to_api_repr()
                if table.time_partitioning
                else None,
                'clustering_fields': table.clustering_fields,
                'labels': table.labels,
                'view_query': table.view_query,
                'table_type': table.table_type,
            }

            return info

        except GoogleCloudError as e:
            logger.error(f'Error getting table info for {dataset_id}.{table_id}: {e}')
            raise
        except Exception as e:
            logger.error(
                f'Unexpected error getting table info for {dataset_id}.{table_id}: {e}'
            )
            raise

    def get_table_size(self, dataset_id: str, table_id: str) -> Dict[str, Any]:
        """
        Get table size information.

        Args:
            dataset_id: Dataset ID
            table_id: Table ID

        Returns:
            Dictionary containing size information
        """
        try:
            table = self.get_table(dataset_id, table_id)

            size_info = {
                'table_id': table.table_id,
                'dataset_id': table.dataset_id,
                'num_rows': table.num_rows,
                'num_bytes': table.num_bytes,
                'num_megabytes': table.num_bytes / (1024 * 1024)
                if table.num_bytes
                else 0,
                'num_gigabytes': table.num_bytes / (1024 * 1024 * 1024)
                if table.num_bytes
                else 0,
            }

            return size_info

        except GoogleCloudError as e:
            logger.error(f'Error getting table size for {dataset_id}.{table_id}: {e}')
            raise
        except Exception as e:
            logger.error(
                f'Unexpected error getting table size for {dataset_id}.{table_id}: {e}'
            )
            raise

    def get_job_info(self, job_id: str) -> Dict[str, Any]:
        """
        Get information about a BigQuery job.

        Args:
            job_id: Job ID

        Returns:
            Dictionary containing job information
        """
        try:
            job = self.client.get_job(job_id)

            info = {
                'job_id': job.job_id,
                'job_type': job.job_type,
                'state': job.state,
                'created': job.created,
                'started': job.started,
                'ended': job.ended,
                'error_result': job.error_result.to_api_repr()
                if job.error_result
                else None,
                'statistics': job.statistics.to_api_repr() if job.statistics else None,
            }

            return info

        except GoogleCloudError as e:
            logger.error(f'Error getting job info for {job_id}: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error getting job info for {job_id}: {e}')
            raise

    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a running BigQuery job.

        Args:
            job_id: Job ID to cancel

        Returns:
            True if job was cancelled, False otherwise
        """
        try:
            job = self.client.get_job(job_id)
            if job.state == 'RUNNING':
                job.cancel()
                logger.info(f'Cancelled job {job_id}')
                return True
            else:
                logger.info(f'Job {job_id} is not running (state: {job.state})')
                return False

        except GoogleCloudError as e:
            logger.error(f'Error cancelling job {job_id}: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error cancelling job {job_id}: {e}')
            raise

    def list_jobs(
        self,
        state_filter: Optional[str] = None,
        min_creation_time: Optional[datetime] = None,
        max_creation_time: Optional[datetime] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        List BigQuery jobs.

        Args:
            state_filter: Filter jobs by state (RUNNING, DONE, PENDING, etc.)
            min_creation_time: Minimum creation time
            max_creation_time: Maximum creation time
            **kwargs: Additional list parameters

        Returns:
            List of job information dictionaries
        """
        try:
            jobs = []
            for job in self.client.list_jobs(**kwargs):
                # Apply filters
                if state_filter and job.state != state_filter:
                    continue
                if min_creation_time and job.created < min_creation_time:
                    continue
                if max_creation_time and job.created > max_creation_time:
                    continue

                job_info = {
                    'job_id': job.job_id,
                    'job_type': job.job_type,
                    'state': job.state,
                    'created': job.created,
                    'started': job.started,
                    'ended': job.ended,
                    'user_email': job.user_email,
                }
                jobs.append(job_info)

            return jobs

        except GoogleCloudError as e:
            logger.error(f'Error listing jobs: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error listing jobs: {e}')
            raise

    def get_query_plan(
        self, query: str, use_legacy_sql: bool = False
    ) -> Dict[str, Any]:
        """
        Get the query execution plan for a BigQuery query.

        Args:
            query: SQL query
            use_legacy_sql: Whether to use legacy SQL

        Returns:
            Dictionary containing query plan information
        """
        try:
            job_config = QueryJobConfig(use_legacy_sql=use_legacy_sql, dry_run=True)
            query_job = self.client.query(query, job_config=job_config)

            # Get query statistics
            stats = query_job.statistics

            plan_info = {
                'total_bytes_processed': stats.total_bytes_processed,
                'total_bytes_billed': stats.total_bytes_billed,
                'billing_tier': stats.billing_tier,
                'cache_hit': stats.cache_hit,
                'num_dml_affected_rows': stats.num_dml_affected_rows,
                'ddl_operation_performed': stats.ddl_operation_performed,
                'ddl_target_table': stats.ddl_target_table.to_api_repr()
                if stats.ddl_target_table
                else None,
                'ddl_target_routine': stats.ddl_target_routine.to_api_repr()
                if stats.ddl_target_routine
                else None,
                'ddl_target_dataset': stats.ddl_target_dataset.to_api_repr()
                if stats.ddl_target_dataset
                else None,
                'ddl_target_view': stats.ddl_target_view.to_api_repr()
                if stats.ddl_target_view
                else None,
                'statement_type': stats.statement_type,
                'estimated_bytes_processed': stats.estimated_bytes_processed,
            }

            return plan_info

        except GoogleCloudError as e:
            logger.error(f'Error getting query plan: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error getting query plan: {e}')
            raise

    async def test_connection(self) -> bool:
        """
        Test the BigQuery connection by executing a simple query.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            # Execute a simple query to test connection
            query = 'SELECT 1 as test'
            await self.execute_query(query)
            logger.info('BigQuery connection test successful')
            return True

        except Exception as e:
            logger.error(f'BigQuery connection test failed: {e}')
            return False

    def get_project_info(self) -> Dict[str, Any]:
        """
        Get information about the current BigQuery project.

        Returns:
            Dictionary containing project information
        """
        try:
            project = self.client.project

            info = {
                'project_id': project,
                'location': self.location,
                'client_location': self.client.location,
            }

            return info

        except GoogleCloudError as e:
            logger.error(f'Error getting project info: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error getting project info: {e}')
            raise

    def create_view(
        self,
        dataset_id: str,
        view_id: str,
        query: str,
        description: Optional[str] = None,
        use_legacy_sql: bool = False,
        **kwargs,
    ) -> Table:
        """
        Create a BigQuery view.

        Args:
            dataset_id: Dataset ID
            view_id: View ID
            query: SQL query for the view
            description: View description
            use_legacy_sql: Whether to use legacy SQL
            **kwargs: Additional view configuration parameters

        Returns:
            Created Table object (view)
        """
        try:
            table_ref = self._get_table_ref(dataset_id, view_id)
            view = Table(table_ref)

            view.view_query = query
            view.view_use_legacy_sql = use_legacy_sql

            if description:
                view.description = description

            # Set additional properties
            for key, value in kwargs.items():
                if hasattr(view, key):
                    setattr(view, key, value)

            view = self.client.create_table(view, timeout=self.timeout)
            logger.info(f'Created view {dataset_id}.{view_id}')
            return view

        except GoogleCloudError as e:
            logger.error(f'Error creating view {dataset_id}.{view_id}: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error creating view {dataset_id}.{view_id}: {e}')
            raise

    def create_materialized_view(
        self,
        dataset_id: str,
        view_id: str,
        query: str,
        description: Optional[str] = None,
        enable_refresh: bool = True,
        refresh_interval_ms: int = 1800000,  # 30 minutes
        **kwargs,
    ) -> Table:
        """
        Create a BigQuery materialized view.

        Args:
            dataset_id: Dataset ID
            view_id: View ID
            query: SQL query for the materialized view
            description: View description
            enable_refresh: Whether to enable automatic refresh
            refresh_interval_ms: Refresh interval in milliseconds
            **kwargs: Additional view configuration parameters

        Returns:
            Created Table object (materialized view)
        """
        try:
            table_ref = self._get_table_ref(dataset_id, view_id)
            view = Table(table_ref)

            view.view_query = query
            view.materialized_view = {
                'enable_refresh': enable_refresh,
                'refresh_interval_ms': refresh_interval_ms,
            }

            if description:
                view.description = description

            # Set additional properties
            for key, value in kwargs.items():
                if hasattr(view, key):
                    setattr(view, key, value)

            view = self.client.create_table(view, timeout=self.timeout)
            logger.info(f'Created materialized view {dataset_id}.{view_id}')
            return view

        except GoogleCloudError as e:
            logger.error(
                f'Error creating materialized view {dataset_id}.{view_id}: {e}'
            )
            raise
        except Exception as e:
            logger.error(
                f'Unexpected error creating materialized view {dataset_id}.{view_id}: {e}'
            )
            raise

    async def refresh_materialized_view(self, dataset_id: str, view_id: str) -> bool:
        """
        Refresh a BigQuery materialized view.

        Args:
            dataset_id: Dataset ID
            view_id: View ID

        Returns:
            True if refresh was successful, False otherwise
        """
        try:
            table_ref = self._get_table_ref(dataset_id, view_id)
            table = self.client.get_table(table_ref)

            if not table.materialized_view:
                logger.warning(
                    f'Table {dataset_id}.{view_id} is not a materialized view'
                )
                return False

            # Create a query job to refresh the materialized view
            query = f'SELECT * FROM `{self.project_id}.{dataset_id}.{view_id}` LIMIT 0'
            await self.execute_query(query)

            logger.info(f'Refreshed materialized view {dataset_id}.{view_id}')
            return True

        except GoogleCloudError as e:
            logger.error(
                f'Error refreshing materialized view {dataset_id}.{view_id}: {e}'
            )
            raise
        except Exception as e:
            logger.error(
                f'Unexpected error refreshing materialized view {dataset_id}.{view_id}: {e}'
            )
            raise

    async def execute_batch_queries(
        self, queries: List[str], use_legacy_sql: bool = False, **kwargs
    ) -> List[QueryJob]:
        """
        Execute multiple queries in sequence.

        Args:
            queries: List of SQL queries to execute
            use_legacy_sql: Whether to use legacy SQL
            **kwargs: Additional query configuration parameters

        Returns:
            List of QueryJob objects
        """
        jobs = []
        for i, query in enumerate(queries):
            try:
                logger.info(f'Executing query {i+1}/{len(queries)}')
                job = await self.execute_query(
                    query, use_legacy_sql=use_legacy_sql, **kwargs
                )
                jobs.append(job)
            except Exception as e:
                logger.error(f'Error executing query {i+1}: {e}')
                raise

        return jobs

    def get_table_schema(self, dataset_id: str, table_id: str) -> List[Dict[str, Any]]:
        """
        Get the schema of a BigQuery table.

        Args:
            dataset_id: Dataset ID
            table_id: Table ID

        Returns:
            List of field definitions as dictionaries
        """
        try:
            table = self.get_table(dataset_id, table_id)
            schema = []

            for field in table.schema:
                field_info = {
                    'name': field.name,
                    'type': field.field_type,
                    'mode': field.mode,
                    'description': field.description,
                }

                if field.fields:  # Nested fields
                    field_info['fields'] = [
                        {
                            'name': nested_field.name,
                            'type': nested_field.field_type,
                            'mode': nested_field.mode,
                            'description': nested_field.description,
                        }
                        for nested_field in field.fields
                    ]

                schema.append(field_info)

            return schema

        except GoogleCloudError as e:
            logger.error(f'Error getting schema for {dataset_id}.{table_id}: {e}')
            raise
        except Exception as e:
            logger.error(
                f'Unexpected error getting schema for {dataset_id}.{table_id}: {e}'
            )
            raise

    def estimate_query_cost(
        self, query: str, use_legacy_sql: bool = False
    ) -> Dict[str, Any]:
        """
        Estimate the cost of running a query (dry run).

        Args:
            query: SQL query to estimate
            use_legacy_sql: Whether to use legacy SQL

        Returns:
            Dictionary containing cost estimation information
        """
        try:
            plan = self.get_query_plan(query, use_legacy_sql=use_legacy_sql)

            # BigQuery pricing (as of 2024): $5 per TB processed
            bytes_processed = plan['total_bytes_processed']
            tb_processed = bytes_processed / (1024**4)  # Convert to TB
            estimated_cost = tb_processed * 5  # $5 per TB

            cost_info = {
                'bytes_processed': bytes_processed,
                'tb_processed': tb_processed,
                'estimated_cost_usd': estimated_cost,
                'billing_tier': plan['billing_tier'],
                'cache_hit': plan['cache_hit'],
            }

            return cost_info

        except GoogleCloudError as e:
            logger.error(f'Error estimating query cost: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error estimating query cost: {e}')
            raise

    def get_table_partition_info(
        self, dataset_id: str, table_id: str
    ) -> Dict[str, Any]:
        """
        Get information about table partitions.

        Args:
            dataset_id: Dataset ID
            table_id: Table ID

        Returns:
            Dictionary containing partition information
        """
        try:
            table = self.get_table(dataset_id, table_id)

            if not table.time_partitioning:
                return {'has_partitioning': False}

            # Query to get partition information
            partition_query = f"""
            SELECT
                partition_id,
                creation_time,
                last_modified_time,
                total_rows,
                total_logical_bytes,
                total_physical_bytes
            FROM `{self.project_id}.{dataset_id}.{table_id}$__PARTITIONS_SUMMARY__`
            ORDER BY partition_id DESC
            LIMIT 100
            """

            try:
                partitions = self.execute_query(partition_query)
            except Exception as e:
                print(e)
                # If partition summary table doesn't exist, return basic info
                partitions = []

            partition_info = {
                'has_partitioning': True,
                'partitioning_type': table.time_partitioning.type_,
                'partitioning_field': table.time_partitioning.field,
                'partitioning_expiration_ms': table.time_partitioning.expiration_ms,
                'partitions': partitions,
            }

            return partition_info

        except GoogleCloudError as e:
            logger.error(
                f'Error getting partition info for {dataset_id}.{table_id}: {e}'
            )
            raise
        except Exception as e:
            logger.error(
                f'Unexpected error getting partition info for {dataset_id}.{table_id}: {e}'
            )
            raise

    async def optimize_table(self, dataset_id: str, table_id: str) -> bool:
        """
        Optimize a BigQuery table by running OPTIMIZE command.

        Args:
            dataset_id: Dataset ID
            table_id: Table ID

        Returns:
            True if optimization was successful, False otherwise
        """
        try:
            optimize_query = f'OPTIMIZE `{self.project_id}.{dataset_id}.{table_id}`'
            await self.execute_query(optimize_query)

            logger.info(f'Optimized table {dataset_id}.{table_id}')
            return True

        except GoogleCloudError as e:
            logger.error(f'Error optimizing table {dataset_id}.{table_id}: {e}')
            raise
        except Exception as e:
            logger.error(
                f'Unexpected error optimizing table {dataset_id}.{table_id}: {e}'
            )
            raise

    def get_query_history(
        self,
        max_results: int = 100,
        state_filter: Optional[str] = None,
        min_creation_time: Optional[datetime] = None,
        max_creation_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get detailed query history with filtering options.

        Args:
            max_results: Maximum number of results to return
            state_filter: Filter by job state (RUNNING, DONE, PENDING, etc.)
            min_creation_time: Minimum creation time
            max_creation_time: Maximum creation time

        Returns:
            List of detailed job information dictionaries
        """
        try:
            jobs = self.list_jobs(
                max_results=max_results,
                state_filter=state_filter,
                min_creation_time=min_creation_time,
                max_creation_time=max_creation_time,
            )

            detailed_jobs = []
            for job_info in jobs:
                try:
                    detailed_job = self.get_job_info(job_info['job_id'])
                    detailed_jobs.append(detailed_job)
                except Exception as e:
                    logger.warning(
                        f"Could not get detailed info for job {job_info['job_id']}: {e}"
                    )
                    detailed_jobs.append(job_info)

            return detailed_jobs

        except GoogleCloudError as e:
            logger.error(f'Error getting query history: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error getting query history: {e}')
            raise

    def wait_for_job_completion(
        self, job_id: str, timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Wait for a BigQuery job to complete and return the result.

        Args:
            job_id: Job ID to wait for
            timeout: Timeout in seconds (uses client timeout if None)

        Returns:
            Dictionary containing job result information
        """
        try:
            job = self.client.get_job(job_id)
            timeout = timeout or self.timeout

            # Wait for job completion
            job.result(timeout=timeout)

            result_info = {
                'job_id': job.job_id,
                'state': job.state,
                'created': job.created,
                'started': job.started,
                'ended': job.ended,
                'error_result': job.error_result.to_api_repr()
                if job.error_result
                else None,
            }

            return result_info

        except GoogleCloudError as e:
            logger.error(f'Error waiting for job {job_id}: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error waiting for job {job_id}: {e}')
            raise

    def execute_transaction(
        self, statements: List[str], use_legacy_sql: bool = False, **kwargs
    ) -> bigquery.job.QueryJob:
        """
        Execute multiple SQL statements as a single transaction using BigQuery scripting.
        All statements are wrapped in a BEGIN ... COMMIT block.
        If any statement fails, the transaction is rolled back.

        Args:
            statements: List of SQL statements to execute transactionally
            use_legacy_sql: Whether to use legacy SQL (default: False)
            **kwargs: Additional query configuration parameters

        Returns:
            QueryJob object for the transaction script
        """
        if not statements:
            raise ValueError('No statements provided for transaction.')
        script = 'BEGIN\n' + '\n'.join(statements) + '\nCOMMIT;'
        try:
            job_config = bigquery.QueryJobConfig(
                use_legacy_sql=use_legacy_sql, **kwargs
            )
            query_job = self.client.query(script, job_config=job_config)
            query_job.result(timeout=self.timeout)
            logger.info('Transaction committed successfully.')
            return query_job
        except GoogleCloudError as e:
            logger.error(f'BigQuery transaction execution error: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error executing BigQuery transaction: {e}')
            raise

    def insert_rows_json(
        self,
        table_id: str,
        json_rows: List[Dict[str, Any]],
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Insert rows into a BigQuery table using JSON format.

        Args:
            table_id: Full table ID (project.dataset.table)
            json_rows: List of dictionaries representing rows to insert
            **kwargs: Additional insert configuration parameters

        Returns:
            List of errors (empty list if successful)

        Raises:
            GoogleCloudError: For BigQuery-specific errors
            Exception: For other unexpected errors
        """
        try:
            result = self.client.insert_rows_json(table_id, json_rows, **kwargs)

            # Check if there are any errors in the result
            if result and any(error.get('errors') for error in result):
                error_messages = []
                for row_error in result:
                    if row_error.get('errors'):
                        for error in row_error['errors']:
                            error_messages.append(
                                f"Row {row_error.get('index', 'unknown')}: {error.get('message', 'Unknown error')} "
                                f"(location: {error.get('location', 'unknown')})"
                            )

                error_msg = f"Failed to insert rows into {table_id}. Errors: {'; '.join(error_messages)}"
                logger.error(error_msg)
                raise GoogleCloudError(error_msg)

            logger.info(f'Successfully inserted {len(json_rows)} rows into {table_id}')
            return result
        except GoogleCloudError as e:
            logger.error(f'BigQuery error inserting rows into {table_id}: {e}')
            raise
        except Exception as e:
            logger.error(f'Unexpected error inserting rows into {table_id}: {e}')
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
        for i, table_name in enumerate(table_names):
            join_query = join_query.replace(
                f'JOIN {table_name}',
                f'LEFT JOIN `{table_prefix}{table_name}` AS {aliases[i]}',
            )
            join_query = join_query.replace(f'{table_name}.', f'{aliases[i]}.')
            where_clause = where_clause.replace(f'{table_name}.', f'{aliases[i]}.')

        # Separate projections for parent table 'a' and each child table
        parent_projection = ''
        child_projections = {}  # Dictionary to store projections for each child table

        for col in projection.split(','):
            col = col.strip()
            if col.startswith(f'{aliases[0]}.'):  # Columns from table 'a'
                if parent_projection:
                    parent_projection += ', '
                parent_projection += col
            else:
                table_alias = col.split('.')[0]
                if table_alias not in child_projections:
                    child_projections[table_alias] = ''
                if child_projections[table_alias]:
                    child_projections[table_alias] += ', '
                child_projections[table_alias] += col

        agg_query = []
        for idx, (projection) in enumerate(child_projections.values()):
            agg_query.append(f"""
                        ARRAY_AGG(
                            STRUCT(
                                {projection}
                            )
                        ) as {table_names[idx+1]}
                    """)

        order_by_clause = f'ORDER BY {order_by}' if order_by else ''
        group_by_clause = f'{group_by},' if group_by else ''
        query = f"""
                    SELECT
                        {parent_projection if parent_projection else f'ANY_VALUE({aliases[0]}).*'},
                        {', '.join(agg_query)}
                    FROM `{table_prefix}{table_names[0]}` AS {aliases[0]}
                    {join_query}
                    WHERE {where_clause}
                    GROUP BY {group_by_clause} {parent_projection.split(',')[0] if parent_projection else 'a.id'}
                    {order_by_clause}
                    LIMIT {limit} OFFSET {offset};
                """

        return query
