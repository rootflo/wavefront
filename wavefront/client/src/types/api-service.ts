import { IApiResponse } from "@app/lib/axios";

export interface ApiAuth {
  id: string;
  type: string;
  version: string;
  base_url: string | null;
  path: string;
  additional_headers?: Record<string, string>;
  token?: string | null;
  username?: string;
  password?: string;
  api_key?: string | null;
  api_key_header?: string;
}

export interface ApiEndpoint {
  id: string;
  version: string;
  path: string;
  backend_path: string;
  method: string;
  additional_headers?: Record<string, string>;
  backend_query_params?: Record<string, any>;
  output_mapper_enabled: boolean;
  output_mapper?: Record<string, string>;
}

export interface ApiServiceItem {
  service_id: string;
  base_url: string;
  auth: ApiAuth;
  apis: ApiEndpoint[];
  // Optional fields that might come from YAML but aren't in the example response
  name?: string;
  description?: string;
  version?: string;
  yaml_content?: string;
}

export interface ApiServiceStats {
  total_services: number;
  total_apis: number;
  auth_types: number;
}

// Based on the JSON, the list response has services directly in data
export interface ApiServiceListData {
  services: ApiServiceItem[];
  stats?: ApiServiceStats;
}

// Assuming single service response also has the item directly in data, or we can adjust if we find out otherwise.
// For now, let's assume it matches the list item structure directly in data.
export type ApiServiceData = ApiServiceItem;

export type ApiServiceResponse = IApiResponse<ApiServiceData>;
export type ApiServiceListResponse = IApiResponse<ApiServiceListData>;
