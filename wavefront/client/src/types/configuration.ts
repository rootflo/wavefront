import { IApiResponse } from '@app/lib/axios';

/**
 * Runtime configuration: static reference data a workflow reads at execution
 * time (thresholds, limits, lookup tables). Addressed by
 * (namespace, key); `id` is a surrogate and no endpoint uses it.
 */
export interface ConfigurationListItem {
  id: string;
  namespace: string;
  key: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ConfigurationListData {
  configurations: ConfigurationListItem[];
}

export interface CreateConfigurationRequest {
  namespace: string;
  key: string;
  /** Arbitrary JSON document — the server never interprets it. */
  value: unknown;
  description?: string;
}

export interface UpsertConfigurationRequest {
  value: unknown;
  description?: string;
}

/**
 * The detail read returns the configuration document itself, not a wrapper —
 * it is the same endpoint the `fetch_configuration` workflow node calls, and
 * that node's output has to be the document.
 */
export type ConfigurationValue = unknown;

export type ConfigurationResponse = IApiResponse<ConfigurationListItem>;
export type ConfigurationValueResponse = IApiResponse<ConfigurationValue>;
export type ConfigurationListResponse = IApiResponse<ConfigurationListData>;
