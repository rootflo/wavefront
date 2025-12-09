import { IApiResponse } from "@app/lib/axios";

export interface Workflow {
  id: string;
  name: string;
  namespace: string;
  created_at: string;
  updated_at: string;
  yaml_content: string;
}

export interface WorkflowInferenceData {
  message: string;
  data: {
    result: string | Record<string, unknown>;
    workflow_id: string;
    namespace: string;
    execution_time: number;
  };
}

export interface WorkflowData {
  message: string;
  data: {
    id: string;
    name: string;
    namespace: string;
    created_at: string;
    updated_at: string;
    yaml_content?: string;
  };
}

export interface WorkflowListItem {
  id: string;
  name: string;
  namespace: string;
  created_at: string;
  updated_at: string;
}

export interface WorkflowPipelineListItem {
  id: string;
  name: string;
  description: string | null;
  location: string;
  workflow_id?: string;
  retry_policy: string | null;
  timeout: string | null;
  concurrency_limit: number;
  created_at: string;
  updated_at: string;
}

export interface WorkflowPipelineListData {
  workflow_pipelines: WorkflowPipelineListItem[];
  total_count: number;
  page_size: number;
  page_number: number;
  total_pages: number;
}

export interface WorkflowListData {
  message: string;
  data: {
    workflows: WorkflowListItem[];
    count: number;
  };
}

// SSE Event Types
export interface WorkflowEventBase {
  event_type: string;
  timestamp: number;
  workflow_id: string;
  namespace: string;
  node_name?: string;
  node_type?: string;
  execution_time?: number;
  error?: string;
  router_choice?: string;
  metadata?: Record<string, unknown>;
}

export interface WorkflowStartedEvent extends WorkflowEventBase {
  event_type: "workflow_started";
}

export interface WorkflowCompletedEvent extends WorkflowEventBase {
  event_type: "workflow_completed";
}

export interface WorkflowFailedEvent extends WorkflowEventBase {
  event_type: "workflow_failed";
  error: string;
}

export interface NodeStartedEvent extends WorkflowEventBase {
  event_type: "node_started";
  node_name: string;
  node_type: string;
}

export interface NodeCompletedEvent extends WorkflowEventBase {
  event_type: "node_completed";
  node_name: string;
  execution_time: number;
}

export interface NodeFailedEvent extends WorkflowEventBase {
  event_type: "node_failed";
  node_name: string;
  error: string;
}

export interface RouterDecisionEvent extends WorkflowEventBase {
  event_type: "router_decision";
  router_choice: string;
}

export interface EdgeTraversedEvent extends WorkflowEventBase {
  event_type: "edge_traversed";
}

export interface OutputEvent extends WorkflowEventBase {
  event_type: "output";
  result: string | object;
}

export interface ErrorEvent {
  event_type: "error";
  error: string;
  timestamp: number;
}

export type WorkflowEvent =
  | WorkflowStartedEvent
  | WorkflowCompletedEvent
  | WorkflowFailedEvent
  | NodeStartedEvent
  | NodeCompletedEvent
  | NodeFailedEvent
  | RouterDecisionEvent
  | EdgeTraversedEvent
  | OutputEvent
  | ErrorEvent;

export interface WorkflowRun {
  id: string;
  workflow_pipeline_id: string;
  status: string;
  start_time: string;
  end_time?: string;
  error?: string;
  output?: unknown;
  created_at?: string;
  updated_at?: string;
  execution_time?: number;
}

export interface WorkflowRunListData {
  workflow_runs: WorkflowRun[];
  total_count: number;
  page_size: number;
  page_number: number;
  total_pages: number;
}

export interface WorkflowRunData {
  workflow_run: WorkflowRun;
}

export type WorkflowInferenceResponse = IApiResponse<WorkflowInferenceData>;
export type WorkflowResponse = IApiResponse<WorkflowData>;
export type WorkflowListResponse = IApiResponse<WorkflowListData>;
export type WorkflowPipelineListResponse =
  IApiResponse<WorkflowPipelineListData>;
export type WorkflowRunListResponse = IApiResponse<WorkflowRunListData>;
export type WorkflowRunResponse = IApiResponse<WorkflowRunData>;
