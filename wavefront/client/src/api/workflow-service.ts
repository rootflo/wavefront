import { IApiResponse } from '@app/lib/axios';
import {
  WorkflowData,
  WorkflowInferenceData,
  WorkflowInferenceResponse,
  WorkflowListData,
  WorkflowListResponse,
  WorkflowPipelineListData,
  WorkflowPipelineListResponse,
  WorkflowResponse,
  WorkflowRunData,
  WorkflowRunListData,
  WorkflowRunListResponse,
  WorkflowRunResponse,
} from '@app/types/workflow';
import { VersionListData, VersionListResponse } from '@app/types/version';
import { AxiosInstance } from 'axios';

export class WorkflowService {
  constructor(private http: AxiosInstance) {}

  async createWorkflow(name: string, yamlContent: string, namespace: string = 'default'): Promise<WorkflowResponse> {
    const response: IApiResponse<WorkflowData> = await this.http.post(
      `/v1/:appId/floware/v1/workflow-management/workflows/${name}`,
      yamlContent,
      {
        headers: {
          'Content-Type': 'text/plain',
        },
        params: {
          namespace,
        },
      }
    );
    return response;
  }

  async getWorkflow(id: string, version?: number): Promise<WorkflowResponse> {
    const response: IApiResponse<WorkflowData> = await this.http.get(
      `/v1/:appId/floware/v1/workflow-management/workflows/${id}`,
      {
        params: version !== undefined ? { version } : undefined,
      }
    );
    return response;
  }

  async updateWorkflow(
    id: string,
    yamlContent: string,
    version?: number,
    createNewVersion: boolean = false
  ): Promise<WorkflowResponse> {
    const params: { version?: number; create_new_version?: boolean } = {};
    if (version !== undefined) params.version = version;
    if (createNewVersion) params.create_new_version = true;

    const response: IApiResponse<WorkflowData> = await this.http.put(
      `/v1/:appId/floware/v1/workflow-management/workflows/${id}`,
      yamlContent,
      {
        headers: {
          'Content-Type': 'text/plain',
        },
        params: Object.keys(params).length > 0 ? params : undefined,
      }
    );
    return response;
  }

  async listWorkflowVersions(id: string): Promise<VersionListResponse> {
    const response: IApiResponse<VersionListData> = await this.http.get(
      `/v1/:appId/floware/v1/workflow-management/workflows/${id}/versions`
    );
    return response;
  }

  async promoteWorkflowVersion(id: string, version: number): Promise<WorkflowResponse> {
    const response: IApiResponse<WorkflowData> = await this.http.patch(
      `/v1/:appId/floware/v1/workflow-management/workflows/${id}/current-version`,
      undefined,
      {
        params: { version },
      }
    );
    return response;
  }

  async deleteWorkflowVersion(id: string, version: number): Promise<WorkflowResponse> {
    const response: IApiResponse<WorkflowData> = await this.http.delete(
      `/v1/:appId/floware/v1/workflow-management/workflows/${id}/versions/${version}`
    );
    return response;
  }

  async runInference(
    id: string,
    inputs: string | unknown[],
    variables: Record<string, unknown> = {},
    outputJsonEnabled: boolean = false,
    version?: number
  ): Promise<WorkflowInferenceResponse> {
    const requestBody: Record<string, unknown> = {
      inputs,
      variables,
      output_json_enabled: outputJsonEnabled,
    };

    const response: IApiResponse<WorkflowInferenceData> = await this.http.post(
      `/v1/:appId/floware/v2/workflows/${id}/inference`,
      requestBody,
      {
        params: version !== undefined ? { version } : undefined,
      }
    );
    return response;
  }

  async listWorkflows(namespace?: string): Promise<WorkflowListResponse> {
    const response: IApiResponse<WorkflowListData> = await this.http.get(
      `/v1/:appId/floware/v1/workflow-management/workflows`,
      {
        params: namespace ? { namespace } : undefined,
      }
    );
    return response;
  }

  async deleteWorkflow(id: string): Promise<WorkflowResponse> {
    const response: IApiResponse<WorkflowData> = await this.http.delete(
      `/v1/:appId/floware/v1/workflow-management/workflows/${id}`
    );
    return response;
  }

  async createWorkflowPipeline(workflowId: string, name: string, workflowVersion?: number): Promise<WorkflowResponse> {
    const requestBody: Record<string, string | number> = {
      name,
      workflow_id: workflowId,
    };
    if (workflowVersion !== undefined) {
      requestBody.workflow_version = workflowVersion;
    }
    const response: IApiResponse<WorkflowData> = await this.http.post(
      `/v1/:appId/floware/v1/workflow-pipelines`,
      requestBody
    );
    return response;
  }

  async updateWorkflowPipeline(
    pipelineId: string,
    payload: {
      name?: string;
      workflow_id?: string;
      workflow_version?: number;
    }
  ): Promise<WorkflowResponse> {
    const response: IApiResponse<WorkflowData> = await this.http.patch(
      `/v1/:appId/floware/v1/workflow-pipelines/${pipelineId}`,
      payload
    );
    return response;
  }

  async listWorkflowPipelines(): Promise<WorkflowPipelineListResponse> {
    const response: IApiResponse<WorkflowPipelineListData> = await this.http.get(
      `/v1/:appId/floware/v1/workflow-pipelines`
    );
    return response;
  }

  async deleteWorkflowPipeline(pipelineId: string): Promise<WorkflowResponse> {
    const response: IApiResponse<WorkflowData> = await this.http.delete(
      `/v1/:appId/floware/v1/workflow-pipelines/${pipelineId}`
    );
    return response;
  }

  async getWorkflowRuns(workflowPipelineId: string, offset: number, limit: number): Promise<WorkflowRunListResponse> {
    const response: IApiResponse<WorkflowRunListData> = await this.http.get(`/v1/:appId/floware/v1/workflow-runs`, {
      params: {
        workflow_pipeline_id: workflowPipelineId,
        offset,
        limit,
      },
    });
    return response;
  }

  async getWorkflowRun(workflowRunId: string): Promise<WorkflowRunResponse> {
    const response: IApiResponse<WorkflowRunData> = await this.http.get(
      `/v1/:appId/floware/v1/workflow-runs/${workflowRunId}`
    );
    return response;
  }

  async submitJobToPipeline(
    workflowPipelineId: string,
    inputs: string | unknown[],
    variables: Record<string, unknown> = {}
  ): Promise<WorkflowInferenceResponse> {
    const requestBody: {
      pipeline_job: {
        inputs: string | unknown[];
        variables: Record<string, unknown>;
      };
    } = {
      pipeline_job: { inputs, variables },
    };

    const response: IApiResponse<WorkflowInferenceData> = await this.http.post(
      `/v1/:appId/floware/v1/workflow-pipelines/${workflowPipelineId}/submit`,
      requestBody
    );
    return response;
  }
}
