import { IApiResponse } from '@app/lib/axios';
import {
  CreateLLMConfigRequest,
  LLMConfigListData,
  LLMConfigListResponse,
  LLMConfigResponse,
  LLMInferenceConfig,
  UpdateLLMConfigRequest,
} from '@app/types/llm-inference-config';
import { AxiosInstance } from 'axios';

export class LLMInferenceService {
  constructor(private http: AxiosInstance) {}

  async createLLMConfig(data: CreateLLMConfigRequest): Promise<LLMConfigResponse> {
    const response: IApiResponse<LLMInferenceConfig> = await this.http.post(
      `/v1/:appId/floware/v1/llm-inference-configs`,
      data
    );
    return response;
  }

  async getLLMConfig(configId: string): Promise<LLMConfigResponse> {
    const response: IApiResponse<LLMInferenceConfig> = await this.http.get(
      `/v1/:appId/floware/v1/llm-inference-configs/${configId}`
    );
    return response;
  }

  async updateLLMConfig(configId: string, data: UpdateLLMConfigRequest): Promise<LLMConfigResponse> {
    const response: IApiResponse<LLMInferenceConfig> = await this.http.patch(
      `/v1/:appId/floware/v1/llm-inference-configs/${configId}`,
      data
    );
    return response;
  }

  async deleteLLMConfig(configId: string): Promise<LLMConfigResponse> {
    const response: IApiResponse<LLMInferenceConfig> = await this.http.delete(
      `/v1/:appId/floware/v1/llm-inference-configs/${configId}`
    );
    return response;
  }

  async listAllLLMConfigs(): Promise<LLMConfigListResponse> {
    const response: IApiResponse<LLMConfigListData> = await this.http.get(
      `/v1/:appId/floware/v1/llm-inference-configs`
    );
    return response;
  }
}
