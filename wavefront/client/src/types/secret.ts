import { IApiResponse } from '@app/lib/axios';

// A named credential API services reference as `${secrets.NAME}`. The value is
// write-only: the API never returns it, only whether one is stored.
export interface Secret {
  id: string;
  name: string;
  description: string | null;
  has_value: boolean;
  created_at: string | null;
  updated_at: string | null;
  /** API services that reference the secret; only on the single-secret read. */
  referenced_by?: string[];
}

export interface CreateSecretRequest {
  name: string;
  value: string;
  description?: string | null;
}

// Omitting `value` keeps the stored value; sending one rotates it.
export interface UpdateSecretRequest {
  value?: string;
  description?: string | null;
}

export interface SecretData {
  secret: Secret;
}

export interface SecretListData {
  secrets: Secret[];
}

/** The `data` of a 409 from delete: the services still referencing the secret. */
export interface SecretInUseData {
  service_ids: string[];
}

export type SecretResponse = IApiResponse<SecretData>;
export type SecretListResponse = IApiResponse<SecretListData>;

export const SECRET_NAME_PATTERN = /^[A-Z][A-Z0-9_]*$/;

export const secretRef = (name: string) => `\${secrets.${name}}`;

export const hasSecretRef = (value: string) => value.includes('${secrets.');

/** A header whose value is a credential, judged by its name (the server applies the same rule). */
export const isSensitiveHeader = (name: string) => /authorization|token|secret|key|cookie|password/i.test(name);
