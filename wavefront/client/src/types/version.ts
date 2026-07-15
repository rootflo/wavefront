import { IApiResponse } from '@app/lib/axios';

/**
 * A single version of an agent or workflow, as returned by the
 * `.../{id}/versions` list endpoint. Each row is annotated with `is_current`.
 */
export interface EntityVersion {
  id: string;
  version: number;
  is_deleted: boolean;
  is_current: boolean;
  created_at: string;
  updated_at: string;
  // agent_id / workflow_id are passed through by the backend but not required by the UI
  agent_id?: string;
  workflow_id?: string;
}

export interface VersionListData {
  message: string;
  data: {
    versions: EntityVersion[];
    count: number;
  };
}

export type VersionListResponse = IApiResponse<VersionListData>;
