import type { DatasourceTypeValue } from './schemas';

export const DATASOURCE_TYPES: { value: DatasourceTypeValue; label: string }[] = [
  { value: 'gcp_bigquery', label: 'Google BigQuery' },
  { value: 'aws_redshift', label: 'AWS Redshift' },
  { value: 'postgres', label: 'PostgreSQL' },
  { value: 'mssql', label: 'Microsoft SQL Server' },
  { value: 'aws_s3', label: 'AWS S3' },
  { value: 'gcs', label: 'Google Cloud Storage' },
  { value: 'azure_blob_storage', label: 'Azure Blob Storage' },
];

export const DATASOURCE_TYPE_LABELS: Record<string, string> = Object.fromEntries(
  DATASOURCE_TYPES.map(({ value, label }) => [value, label])
);

/** URI scheme the backend returns for uploaded files, per file storage type. */
export const FILE_STORAGE_PROTOCOLS: Record<string, string> = {
  aws_s3: 's3',
  gcs: 'gs',
  azure_blob_storage: 'azure',
};

export const isFileStorageType = (type?: string): boolean => !!type && type in FILE_STORAGE_PROTOCOLS;

export const SAMPLE_CONFIGS: Record<DatasourceTypeValue, Record<string, unknown>> = {
  gcp_bigquery: {
    project_id: 'your-project-id',
    dataset_id: 'your-dataset-id',
    location: 'US',
    credentials_path: '/path/to/service-account.json',
    credentials_json: '{ ... service account JSON ... }',
  },
  aws_redshift: {
    host: 'your-cluster.region.redshift.amazonaws.com',
    port: 5439,
    database: 'your-database',
    user: 'your-username',
    password: 'your-password',
  },
  postgres: {
    host: 'localhost',
    port: 5432,
    database: 'your-database',
    user: 'your-username',
    password: 'your-password',
    schema: 'public',
  },
  mssql: {
    host: 'localhost',
    port: 1433,
    database: 'your-database',
    user: 'your-username',
    password: 'your-password',
    schema: 'dbo',
    encrypt: true,
    trust_server_certificate: false,
  },
  aws_s3: {
    bucket_name: 'your-bucket',
    region_name: 'us-east-1',
    aws_access_key_id: 'your-access-key-id',
    aws_secret_access_key: 'your-secret-access-key',
  },
  gcs: {
    bucket_name: 'your-bucket',
    project_id: 'your-project-id',
    credentials_json: {
      type: 'service_account',
      project_id: 'your-project-id',
      private_key: '-----BEGIN PRIVATE KEY-----\n...',
      client_email: 'name@your-project-id.iam.gserviceaccount.com',
    },
  },
  azure_blob_storage: {
    container_name: 'your-container',
    account_url: 'https://your-account.blob.core.windows.net',
  },
};
