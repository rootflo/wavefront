import { IApiResponse } from '@app/lib/axios';

// Pipeline Status Types
export type PipelineStatus = 'draft' | 'published' | 'paused';

// Pipeline Entity
export interface Pipeline {
  pipeline_id: string;
  project_name: string;
  status: PipelineStatus;
  is_deleted: boolean;
  schedule_interval: string | null;
  description: string | null;
  type?: string;
  start_at?: string;
  created_at: string;
  updated_at: string;
}

// Pipeline CRUD Request Types
export interface CreatePipelineRequest {
  project_name: string;
  description?: string;
  schedule_interval?: string;
  start_at: string;
  type?: string;
}

export interface UpdatePipelineRequest {
  project_name?: string;
  description?: string;
}

export interface UpdateScheduleRequest {
  schedule_interval: string | null;
}

export interface TriggerDagRunRequest {
  conf?: Record<string, any>;
  logical_date?: string;
  note?: string;
}

// Pipeline Response Data Types
export interface PipelineData {
  message: string;
  pipeline: Pipeline;
  compilation_result?: {
    success: boolean;
    message: string;
    manifest_generated?: boolean;
  };
  deployment_details?: {
    dag_deployed: boolean;
  };
  cleanup_operations?: {
    dag_paused: boolean;
    dev_files_deleted: boolean;
    composer_files_deleted: boolean;
    cache_invalidated: boolean;
  };
}

export interface PipelinesListData {
  pipelines: Pipeline[];
  total_count: number;
}

export interface TriggerDagRunData {
  message: string;
  dag_run_id: string;
  pipeline_id: string;
  dag_id: string;
  state: string;
  logical_date: string;
  execution_date: string;
  conf?: Record<string, any>;
}

// Pipeline API Response Types
export type PipelineResponse = IApiResponse<PipelineData>;
export type PipelinesListResponse = IApiResponse<PipelinesListData>;
export type TriggerDagRunResponse = IApiResponse<TriggerDagRunData>;

// Pipeline File Types
export type FileType = 'model' | 'test' | 'macro' | 'config' | 'schema' | 'doc' | 'other';

export interface PipelineFile {
  path: string;
  type: FileType;
  size: number;
  content?: string;
}

// File Request Types
export interface FileListParams {
  pipeline_id: string;
}

export interface FileContentParams {
  pipeline_id: string;
  file_path: string;
}

export interface CreateFileRequest {
  pipeline_id: string;
  file_path: string;
  content: string;
}

export interface UpdateFileRequest {
  pipeline_id: string;
  file_path: string;
  content: string;
}

export interface DeleteFileRequest {
  pipeline_id: string;
  file_path: string;
}

// File Response Data Types
export interface FileListData {
  files: PipelineFile[];
  total_count: number;
}

export interface FileContentData {
  path: string;
  content: string;
  type: FileType;
  size: number;
}

export interface FileOperationData {
  message: string;
  file?: {
    path: string;
    type: FileType;
    size: number;
  };
}

// File API Response Types
export type FileListResponse = IApiResponse<FileListData>;
export type FileContentResponse = IApiResponse<FileContentData>;
export type FileOperationResponse = IApiResponse<FileOperationData>;
