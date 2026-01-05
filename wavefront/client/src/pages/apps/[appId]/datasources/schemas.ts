import { z } from 'zod';

export const createDatasourceSchema = z.object({
  name: z.string().min(1, 'Datasource name is required'),
  type: z.enum(['gcp_bigquery', 'aws_redshift']),
  description: z.string().optional(),
  connectionConfig: z
    .string()
    .min(1, 'Connection configuration is required')
    .refine(
      (val) => {
        try {
          JSON.parse(val);
          return true;
        } catch {
          return false;
        }
      },
      {
        message: 'Invalid JSON format',
      }
    ),
});

export type CreateDatasourceInput = z.infer<typeof createDatasourceSchema>;
