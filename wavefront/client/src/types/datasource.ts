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

export interface UploadDatasourceFileData {
  /** datasource://<datasource_id>/<key> */
  path: string;
  /** Provider URI of the stored object, e.g. s3://bucket/key */
  storage_uri: string;
}

export type UploadDatasourceFileResponse = IApiResponse<UploadDatasourceFileData>;

export interface DatasourceFileEntry {
  /** datasource://<datasource_id>/<key> */
  path: string;
  /** Key relative to the datasource base path */
  relative_path: string;
  name: string;
}

export interface ListDatasourceFilesData {
  files: DatasourceFileEntry[];
  page_number: number;
  page_size: number;
  has_next_page: boolean;
}

export type ListDatasourceFilesResponse = IApiResponse<ListDatasourceFilesData>;

/** A sub-folder in a browse listing. */
export interface DatasourceFolderEntry {
  name: string;
  /** Relative to the datasource base path, ending in '/'. */
  prefix: string;
}

/** A file in a browse listing: a list entry plus what the provider reports about it. */
export interface DatasourceBrowseFileEntry extends DatasourceFileEntry {
  size: number | null;
  /** Not reported by S3 when listing. */
  content_type: string | null;
  updated_at: string | null;
}

/** One folder level from `files/browse`: its sub-folders and the files directly in it. */
export interface BrowseDatasourceFilesData {
  prefix: string;
  folders: DatasourceFolderEntry[];
  files: DatasourceBrowseFileEntry[];
  /** Pass back as `page_token` for the next page; null on the last. */
  next_page_token: string | null;
}

export type BrowseDatasourceFilesResponse = IApiResponse<BrowseDatasourceFilesData>;

export interface CreateDatasourceFolderData {
  /** datasource://<datasource_id>/<folder>/ */
  path: string;
  /** Relative to the base path, ending in '/'. */
  prefix: string;
  storage_uri: string;
}

export type CreateDatasourceFolderResponse = IApiResponse<CreateDatasourceFolderData>;

/** One file's outcome in a batch upload, in request order: its paths, or why it failed. */
export interface BatchUploadResult {
  index: number;
  path?: string;
  storage_uri?: string;
  error?: string;
}

export interface BatchUploadDatasourceFilesData {
  uploaded: number;
  failed: number;
  results: BatchUploadResult[];
}

export type BatchUploadDatasourceFilesResponse = IApiResponse<BatchUploadDatasourceFilesData>;

export interface DeleteDatasourceFileData {
  path: string;
  storage_uri: string;
}

export type DeleteDatasourceFileResponse = IApiResponse<DeleteDatasourceFileData>;

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
  resources: string[];
}

export interface DatasourceResourceRecordsData {
  records: Record<string, unknown>[];
}

export interface GetDatasourceResourceParams {
  limit?: number;
  offset?: number;
  $select?: string;
  $filter?: string;
  $orderby?: string;
  $groupby?: string;
  $expand?: string;
  $join?: string;
}

/** Insert, update and the multi-table variants all answer with a message, plus a count where the backend has one. */
export interface DatasourceRowsMutationData {
  message: string;
  updated_rows?: number;
}

/** One table's share of an atomic multi-table insert. `data` is one row when `single_row`, else a list of rows. */
export interface DatasourceTableInsert {
  table_name: string;
  data: Record<string, unknown> | Record<string, unknown>[];
  single_row?: boolean;
}

/** One table's share of an atomic multi-table update. */
export interface DatasourceTableUpdate {
  table_name: string;
  filter: string;
  data: Record<string, unknown>;
}

export interface ExportDynamicQueryData {
  export_url: string;
}

export type DatasourceAuditOperation = 'insert' | 'update' | 'delete' | 'upload' | 'download';

export interface DatasourceAuditLog {
  id: string;
  batch_id: string | null;
  datasource_id: string;
  datasource_type: string;
  table_name: string | null;
  operation: DatasourceAuditOperation;
  filter: string | null;
  filter_params: Record<string, unknown> | null;
  changes: unknown;
  meta: Record<string, unknown> | null;
  rows_affected: number | null;
  user_id: string | null;
  role_id: string | null;
  request_id: string | null;
  created_at: string;
}

export interface ListDatasourceAuditLogsParams {
  datasource_id?: string;
  table_name?: string;
  operation?: DatasourceAuditOperation;
  user_id?: string;
  from_date?: string;
  to_date?: string;
  /** Columns of the changed row, matched against the filter each change named its rows by. */
  filter_params?: Record<string, string>;
  offset?: number;
  limit?: number;
}

export interface DatasourceAuditLogsData {
  logs: DatasourceAuditLog[];
  count: number;
  total: number;
  offset: number;
  limit: number;
}

export interface DeleteDatasourceResourceRowsData {
  message: string;
  deleted_rows: number;
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
export type DatasourceResourceRecordsResponse = IApiResponse<DatasourceResourceRecordsData>;
export type DeleteDatasourceResourceRowsResponse = IApiResponse<DeleteDatasourceResourceRowsData>;
export type DynamicQueryResponse = IApiResponse<DynamicQueryDataSource>;
export type AllDynamicQueriesResponse = IApiResponse<AllDynamicQueriesData>;
export type ReadDynamicQueryResponse = IApiResponse<ReadDynamicQueryData>;
export type DeleteDynamicQueryResponse = IApiResponse<DeleteDynamicQueryData>;
export type ExecuteDynamicQueryResponse = IApiResponse<ExecuteDynamicQueryData>;
export type DatasourceRowsMutationResponse = IApiResponse<DatasourceRowsMutationData>;
export type ExportDynamicQueryResponse = IApiResponse<ExportDynamicQueryData>;
export type DatasourceAuditLogsResponse = IApiResponse<DatasourceAuditLogsData>;

/** What a dynamic query run takes besides its parameters: the `{{filters}}` filter and paging. */
export interface DynamicQueryRunOptions {
  filter?: string;
  limit?: number;
  offset?: number;
}
