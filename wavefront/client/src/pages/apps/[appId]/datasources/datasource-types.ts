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
