import { IApiResponse } from '@app/lib/axios';
import {
  CreatePipelineRequest,
  FileContentData,
  FileContentResponse,
  FileListData,
  FileListResponse,
  FileOperationData,
  FileOperationResponse,
  PipelineData,
  PipelineResponse,
  PipelinesListData,
  PipelinesListResponse,
  PipelineStatus,
  TriggerDagRunData,
  TriggerDagRunRequest,
  TriggerDagRunResponse,
  UpdatePipelineRequest,
  UpdateScheduleRequest,
} from '@app/types/pipeline';
import { AxiosInstance } from 'axios';

export class DataPipelineService {
  constructor(private http: AxiosInstance) {}

  async listFiles(pipelineId: string): Promise<FileListResponse> {
    const response: IApiResponse<FileListData> = await this.http.get(
      `/v1/:appId/floware/v1/pipelines/${pipelineId}/files`
    );
    return response;
  }

  async getFileContent(pipelineId: string, filePath: string): Promise<FileContentResponse> {
    const response: IApiResponse<FileContentData> = await this.http.get(
      `/v1/:appId/floware/v1/pipelines/${pipelineId}/files/${filePath}`
    );
    return response;
  }

  async createFile(pipelineId: string, filePath: string, content: string): Promise<FileOperationResponse> {
    const response: IApiResponse<FileOperationData> = await this.http.post(
      `/v1/:appId/floware/v1/pipelines/${pipelineId}/files/${filePath}`,
      content,
      {
        headers: {
          'Content-Type': 'text/plain; charset=utf-8',
        },
      }
    );
    return response;
  }

  async updateFile(pipelineId: string, filePath: string, content: string): Promise<FileOperationResponse> {
    const response: IApiResponse<FileOperationData> = await this.http.put(
      `/v1/:appId/floware/v1/pipelines/${pipelineId}/files/${filePath}`,
      content,
      {
        headers: {
          'Content-Type': 'text/plain; charset=utf-8',
        },
      }
    );
    return response;
  }

  async deleteFile(pipelineId: string, filePath: string): Promise<FileOperationResponse> {
    const response: IApiResponse<FileOperationData> = await this.http.delete(
      `/v1/:appId/floware/v1/pipelines/${pipelineId}/files/${filePath}`
    );
    return response;
  }

  async createPipeline(data: CreatePipelineRequest): Promise<PipelineResponse> {
    const response: IApiResponse<PipelineData> = await this.http.post(`/v1/:appId/floware/v1/pipelines`, data);
    return response;
  }

  async listPipelines(status?: PipelineStatus): Promise<PipelinesListResponse> {
    const params = status ? { status } : undefined;
    const response: IApiResponse<PipelinesListData> = await this.http.get(`/v1/:appId/floware/v1/pipelines`, {
      params,
    });
    return response;
  }

  async getPipeline(pipelineId: string): Promise<PipelineResponse> {
    const response: IApiResponse<PipelineData> = await this.http.get(`/v1/:appId/floware/v1/pipelines/${pipelineId}`);
    return response;
  }

  async updatePipeline(pipelineId: string, data: UpdatePipelineRequest): Promise<PipelineResponse> {
    const response: IApiResponse<PipelineData> = await this.http.patch(
      `/v1/:appId/floware/v1/pipelines/${pipelineId}`,
      data
    );
    return response;
  }

  async updateSchedule(pipelineId: string, data: UpdateScheduleRequest): Promise<PipelineResponse> {
    const response: IApiResponse<PipelineData> = await this.http.patch(
      `/v1/:appId/floware/v1/pipelines/${pipelineId}/schedule`,
      data
    );
    return response;
  }

  async publishPipeline(namespace: string, pipelineId: string): Promise<PipelineResponse> {
    const response: IApiResponse<PipelineData> = await this.http.post(
      `/v1/:appId/floware/v1/namespaces/${namespace}/pipelines/${pipelineId}/publish`
    );
    return response;
  }

  async pausePipeline(namespace: string, pipelineId: string): Promise<PipelineResponse> {
    const response: IApiResponse<PipelineData> = await this.http.post(
      `/v1/:appId/floware/v1/namespaces/${namespace}/pipelines/${pipelineId}/pause`
    );
    return response;
  }

  async unpausePipeline(namespace: string, pipelineId: string): Promise<PipelineResponse> {
    const response: IApiResponse<PipelineData> = await this.http.post(
      `/v1/:appId/floware/v1/namespaces/${namespace}/pipelines/${pipelineId}/unpause`
    );
    return response;
  }

  async triggerDagRun(
    namespace: string,
    pipelineId: string,
    data?: TriggerDagRunRequest
  ): Promise<TriggerDagRunResponse> {
    const response: IApiResponse<TriggerDagRunData> = await this.http.post(
      `/v1/:appId/floware/v1/namespaces/${namespace}/pipelines/${pipelineId}/trigger`,
      data || {}
    );
    return response;
  }

  async deletePipeline(namespace: string, pipelineId: string): Promise<PipelineResponse> {
    const response: IApiResponse<PipelineData> = await this.http.delete(
      `/v1/:appId/floware/v1/namespaces/${namespace}/pipelines/${pipelineId}`
    );
    return response;
  }
}
