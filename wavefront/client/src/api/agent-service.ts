import { IApiResponse } from '@app/lib/axios';
import {
  AgentData,
  AgentListData,
  AgentListResponse,
  AgentResponse,
  InferenceData,
  InferenceResponse,
} from '@app/types/agent';
import { AxiosInstance } from 'axios';

export class AgentService {
  constructor(private http: AxiosInstance) {}

  async createAgent(name: string, yamlContent: string, namespace: string = 'default'): Promise<AgentResponse> {
    const response: IApiResponse<AgentData> = await this.http.post(
      `/v1/:appId/floware/v1/agent-management/agents/${name}`,
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

  async getAgent(id: string): Promise<AgentResponse> {
    const response: IApiResponse<AgentData> = await this.http.get(
      `/v1/:appId/floware/v1/agent-management/agents/${id}`
    );
    return response;
  }

  async updateAgent(id: string, yamlContent: string): Promise<AgentResponse> {
    const response: IApiResponse<AgentData> = await this.http.put(
      `/v1/:appId/floware/v1/agent-management/agents/${id}`,
      yamlContent,
      {
        headers: {
          'Content-Type': 'text/plain',
        },
      }
    );
    return response;
  }

  async runInference(
    id: string,
    variables: Record<string, unknown> = {},
    inputs: string | string[],
    llmInferenceConfigId?: string,
    toolNames?: string[]
  ): Promise<InferenceResponse> {
    const requestBody: {
      variables: Record<string, unknown>;
      inputs: string | string[];
      llm_inference_config_id?: string;
      tool_names?: string[];
      output_json_enabled: boolean;
    } = {
      variables,
      inputs,
      output_json_enabled: false,
    };

    if (llmInferenceConfigId) {
      requestBody.llm_inference_config_id = llmInferenceConfigId;
    }

    if (toolNames && toolNames.length > 0) {
      requestBody.tool_names = toolNames;
    }

    const response: IApiResponse<InferenceData> = await this.http.post(
      `/v1/:appId/floware/v2/agents/${id}/inference`,
      requestBody
    );
    return response;
  }

  async listAgents(namespace?: string): Promise<AgentListResponse> {
    const response: IApiResponse<AgentListData> = await this.http.get(`/v1/:appId/floware/v1/agent-management/agents`, {
      params: namespace ? { namespace } : undefined,
    });
    return response;
  }

  async deleteAgent(id: string): Promise<AgentResponse> {
    const response: IApiResponse<AgentData> = await this.http.delete(
      `/v1/:appId/floware/v1/agent-management/agents/${id}`
    );
    return response;
  }
}
