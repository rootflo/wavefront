import { IApiResponse } from '@app/lib/axios';

export interface Datasource {
  id: string;
  name: string;
  type: string;
  config: Record<string, unknown>;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

export interface CreateDatasourceRequest {
  name: string;
  type: string;
  config: string; // JSON string as per API
  description?: string;
}

export interface UpdateDatasourceRequest {
  name: string;
  type: string;
  config: string; // JSON string as per API
  description?: string;
}

export type TestDatasourceData = boolean;

export interface DatasourceData {
  status: 'success' | 'error';
  data: {
    message?: string;
    datasource_id?: string;
  };
}

export interface DatasourceListData {
  status: 'success' | 'error';
  data: {
    datasources: Datasource[];
  };
}

export interface DatasourceResourcesData {
  status: 'success' | 'error';
  data: {
    resources: string[];
  };
}
export interface DynamicQueryDataSource {
  status: 'success' | 'error';
  data: {
    message: string;
  };
}

export interface DynamicQuery {
  version: string;
  file: string;
  full_path: string;
}
export interface AllDynamicQueriesData {
  yamls: DynamicQuery[];
  has_more: boolean;
  page_number: number;
  page_size: number;
  total_count: number;
}
export interface DynamicQueryItem {
  id: string;
  query: string;
  parameters?: Array<{ name: string; type: string }>;
  description?: string;
}
export interface ReadDynamicQueryData {
  yaml_name: string;
  yaml_query: DynamicQueryItem[];
}
export interface DeleteDynamicQueryData {
  message: string;
}
export interface ExecuteDynamicQueryData {
  results: Record<string, unknown>[];
}

export type TestDatasourceResponse = IApiResponse<TestDatasourceData>;
export type DatasourceResponse = IApiResponse<DatasourceData>;
export type DatasourceListResponse = IApiResponse<DatasourceListData>;
export type DatasourceResourcesResponse = IApiResponse<DatasourceResourcesData>;
export type DynamicQueryResponse = IApiResponse<DynamicQueryDataSource>;
export type AllDynamicQueriesResponse = IApiResponse<AllDynamicQueriesData>;
export type ReadDynamicQueryResponse = IApiResponse<ReadDynamicQueryData>;
export type DeleteDynamicQueryResponse = IApiResponse<DeleteDynamicQueryData>;
export type ExecuteDynamicQueryResponse = IApiResponse<ExecuteDynamicQueryData>;
