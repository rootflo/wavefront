import { IApiResponse } from '@app/lib/axios';

export interface Datasource {
  id: string;
  name: string;
  type: string;
  config: Record<string, any>;
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
export interface YamlDataSource {
  status: 'success' | 'error';
  data: {
    message: string;
  };
}

export interface Yaml {
  version: string;
  file: string;
  full_path: string;
}
export interface AllYamlsData {
  yamls: Yaml[];
  has_more: boolean;
  page_number: number;
  page_size: number;
  total_count: number;
}
export interface YamlReadData {
  id: string;
  query: string;
  parameters?: Array<{ name: string; type: string }>;
  description?: string;
}
export interface ReadYamlData {
  yaml_name: string;
  yaml_query: YamlReadData[];
}
export interface DeleteYamlData {
  message: string;
}
export interface ExecuteYamlData {
  results: Record<string, any>[];
}

export type TestDatasourceResponse = IApiResponse<TestDatasourceData>;
export type DatasourceResponse = IApiResponse<DatasourceData>;
export type DatasourceListResponse = IApiResponse<DatasourceListData>;
export type DatasourceResourcesResponse = IApiResponse<DatasourceResourcesData>;
export type YamlResponse = IApiResponse<YamlDataSource>;
export type AllYamlsResponse = IApiResponse<AllYamlsData>;
export type ReadYamlResponse = IApiResponse<ReadYamlData>;
export type DeleteYamlResponse = IApiResponse<DeleteYamlData>;
export type ExecuteYamlResponse = IApiResponse<ExecuteYamlData>;
