import { z } from 'zod';

// The connection settings themselves are per-type form fields (see datasource-config.ts), checked when saving.
export const createDatasourceSchema = z.object({
  name: z.string().trim().min(1, 'Datasource name is required'),
  type: z.enum(['gcp_bigquery', 'aws_redshift', 'postgres', 'mssql', 'aws_s3', 'gcs', 'azure_blob_storage']),
  description: z.string().optional(),
});

export type CreateDatasourceInput = z.infer<typeof createDatasourceSchema>;

export type DatasourceTypeValue = CreateDatasourceInput['type'];
