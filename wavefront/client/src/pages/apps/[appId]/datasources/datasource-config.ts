// The connection settings each datasource type takes, as form fields rather than hand-written JSON.
// Mirrors the backend's config classes (plugins/datasource/*/config.py and file_storage/config.py).

import type { DatasourceTypeValue } from './schemas';

export type ConfigFieldKind = 'text' | 'password' | 'number' | 'boolean' | 'json';

export interface ConfigField {
  key: string;
  label: string;
  kind: ConfigFieldKind;
  required?: boolean;
  placeholder?: string;
  help?: string;
  /** Pre-filled for a new datasource. */
  defaultValue?: string | boolean;
  /** Tucked under "More settings" so the common case stays short. */
  advanced?: boolean;
  /** Takes the full row (long values, JSON). */
  wide?: boolean;
}

/** What the server returns in place of a saved secret. Sent back unchanged, it keeps that secret. */
export const SECRET_MASK = '********';

/** Values as the form holds them: text for text-like fields, true/false for switches. */
export type ConfigValues = Record<string, string | boolean>;

const host = (placeholder: string): ConfigField => ({
  key: 'host',
  label: 'Host',
  kind: 'text',
  required: true,
  placeholder,
  wide: true,
});
const port = (defaultValue: string): ConfigField => ({
  key: 'port',
  label: 'Port',
  kind: 'number',
  required: true,
  defaultValue,
});
const database: ConfigField = { key: 'database', label: 'Database', kind: 'text', required: true };
const user: ConfigField = { key: 'user', label: 'Username', kind: 'text', required: true };
const password: ConfigField = { key: 'password', label: 'Password', kind: 'password', required: true };
const basePath: ConfigField = {
  key: 'base_path',
  label: 'Base path',
  kind: 'text',
  placeholder: 'e.g. uploads/',
  help: 'Keep this datasource inside one folder of the bucket. Leave empty for the whole bucket.',
  advanced: true,
};
const serviceAccountJson = (help: string): ConfigField => ({
  key: 'credentials_json',
  label: 'Service account key',
  kind: 'json',
  help,
  wide: true,
});

export const CONFIG_FIELDS: Record<DatasourceTypeValue, ConfigField[]> = {
  gcp_bigquery: [
    { key: 'project_id', label: 'Project ID', kind: 'text', required: true, placeholder: 'my-project' },
    { key: 'dataset_id', label: 'Dataset ID', kind: 'text', required: true, placeholder: 'analytics' },
    { key: 'location', label: 'Location', kind: 'text', required: true, defaultValue: 'US', placeholder: 'US' },
    serviceAccountJson('Paste the JSON key, or upload the file. Leave empty to use the server’s own credentials.'),
    {
      key: 'credentials_path',
      label: 'Key file path on the server',
      kind: 'text',
      placeholder: '/secrets/service-account.json',
      help: 'Instead of a key above: a key file the server can read.',
      advanced: true,
      wide: true,
    },
  ],
  aws_redshift: [host('my-cluster.abc123.us-east-1.redshift.amazonaws.com'), port('5439'), database, user, password],
  postgres: [
    host('db.example.com'),
    port('5432'),
    database,
    user,
    password,
    { key: 'schema', label: 'Schema', kind: 'text', defaultValue: 'public', advanced: true },
  ],
  mssql: [
    host('sql.example.com'),
    port('1433'),
    database,
    user,
    password,
    { key: 'schema', label: 'Schema', kind: 'text', defaultValue: 'dbo', advanced: true },
    { key: 'encrypt', label: 'Encrypt the connection', kind: 'boolean', defaultValue: true, advanced: true },
    {
      key: 'trust_server_certificate',
      label: 'Trust the server certificate',
      kind: 'boolean',
      defaultValue: false,
      help: 'Only for servers with a self-signed certificate.',
      advanced: true,
    },
  ],
  aws_s3: [
    { key: 'bucket_name', label: 'Bucket', kind: 'text', required: true, placeholder: 'my-bucket' },
    { key: 'region_name', label: 'Region', kind: 'text', placeholder: 'us-east-1' },
    {
      key: 'aws_access_key_id',
      label: 'Access key ID',
      kind: 'text',
      help: 'Leave both keys empty to use the server’s own AWS credentials.',
    },
    { key: 'aws_secret_access_key', label: 'Secret access key', kind: 'password' },
    basePath,
  ],
  gcs: [
    { key: 'bucket_name', label: 'Bucket', kind: 'text', required: true, placeholder: 'my-bucket' },
    { key: 'project_id', label: 'Project ID', kind: 'text', placeholder: 'my-project' },
    serviceAccountJson('Paste the JSON key, or upload the file. Leave empty to use the server’s own credentials.'),
    basePath,
  ],
  azure_blob_storage: [
    { key: 'container_name', label: 'Container', kind: 'text', required: true, placeholder: 'my-container' },
    {
      key: 'account_url',
      label: 'Account URL',
      kind: 'text',
      required: true,
      placeholder: 'https://myaccount.blob.core.windows.net',
    },
    {
      key: 'tenant_id',
      label: 'Tenant ID',
      kind: 'text',
      help: 'With client ID and secret, for a service principal. Leave all three empty to use the server’s identity.',
    },
    { key: 'client_id', label: 'Client ID', kind: 'text' },
    { key: 'client_secret', label: 'Client secret', kind: 'password' },
    basePath,
  ],
};

/** A new datasource's starting values: each field's default, or empty. */
export const defaultConfigValues = (type: DatasourceTypeValue): ConfigValues =>
  Object.fromEntries(
    CONFIG_FIELDS[type].map((field) => [field.key, field.defaultValue ?? (field.kind === 'boolean' ? false : '')])
  );

/** A saved config as form values, for editing: JSON shown pretty-printed, numbers as text. */
export const configToValues = (type: DatasourceTypeValue, config: Record<string, unknown>): ConfigValues => {
  const values = defaultConfigValues(type);
  CONFIG_FIELDS[type].forEach((field) => {
    const value = config?.[field.key];
    if (value === undefined || value === null) return;
    if (field.kind === 'boolean') values[field.key] = Boolean(value);
    else if (field.kind === 'json')
      values[field.key] = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
    else values[field.key] = String(value);
  });
  return values;
};

/**
 * The form's values as the config the API takes, or the problem with each field that stops it. Empty optional
 * fields are left out, so the backend applies its own defaults.
 */
export const valuesToConfig = (
  type: DatasourceTypeValue,
  values: ConfigValues
): { config?: Record<string, unknown>; errors: Record<string, string> } => {
  const config: Record<string, unknown> = {};
  const errors: Record<string, string> = {};
  CONFIG_FIELDS[type].forEach((field) => {
    const raw = values[field.key];
    if (field.kind === 'boolean') {
      config[field.key] = Boolean(raw);
      return;
    }
    const text = typeof raw === 'string' ? raw.trim() : '';
    if (!text) {
      if (field.required) errors[field.key] = `${field.label} is required`;
      return;
    }
    if (field.kind === 'number') {
      const number = Number(text);
      if (!Number.isInteger(number) || number <= 0) errors[field.key] = `${field.label} must be a whole number`;
      else config[field.key] = number;
      return;
    }
    if (field.kind === 'json') {
      if (text === SECRET_MASK) {
        config[field.key] = text;
        return;
      }
      try {
        const parsed = JSON.parse(text);
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) throw new Error();
        config[field.key] = parsed;
      } catch {
        errors[field.key] = 'Paste the whole key file: a JSON object starting with {';
      }
      return;
    }
    config[field.key] = text;
  });
  return Object.keys(errors).length ? { errors } : { config, errors };
};
