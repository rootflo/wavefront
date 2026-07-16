import { IApiResponse } from '@app/lib/axios';
import {
  AgentData,
  AgentListData,
  AgentListResponse,
  AgentResponse,
  InferenceData,
  InferenceResponse,
} from '@app/types/agent';
import { VersionListData, VersionListResponse } from '@app/types/version';
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

  async getAgent(id: string, version?: number): Promise<AgentResponse> {
    const response: IApiResponse<AgentData> = await this.http.get(
      `/v1/:appId/floware/v1/agent-management/agents/${id}`,
      {
        params: version !== undefined ? { version } : undefined,
      }
    );
    return response;
  }

  async updateAgent(
    id: string,
    yamlContent: string,
    version?: number,
    createNewVersion: boolean = false
  ): Promise<AgentResponse> {
    const params: { version?: number; create_new_version?: boolean } = {};
    if (version !== undefined) params.version = version;
    if (createNewVersion) params.create_new_version = true;

    const response: IApiResponse<AgentData> = await this.http.put(
      `/v1/:appId/floware/v1/agent-management/agents/${id}`,
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

  async listAgentVersions(id: string): Promise<VersionListResponse> {
    const response: IApiResponse<VersionListData> = await this.http.get(
      `/v1/:appId/floware/v1/agent-management/agents/${id}/versions`
    );
    return response;
  }

  async promoteAgentVersion(id: string, version: number): Promise<AgentResponse> {
    const response: IApiResponse<AgentData> = await this.http.patch(
      `/v1/:appId/floware/v1/agent-management/agents/${id}/current-version`,
      undefined,
      {
        params: { version },
      }
    );
    return response;
  }

  async deleteAgentVersion(id: string, version: number): Promise<AgentResponse> {
    const response: IApiResponse<AgentData> = await this.http.delete(
      `/v1/:appId/floware/v1/agent-management/agents/${id}/versions/${version}`
    );
    return response;
  }

  async runInference(
    id: string,
    inputs: string | string[],
    variables: Record<string, unknown> = {},
    llmInferenceConfigId?: string,
    toolNames?: string[],
    version?: number
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
      requestBody,
      {
        params: version !== undefined ? { version } : undefined,
      }
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
