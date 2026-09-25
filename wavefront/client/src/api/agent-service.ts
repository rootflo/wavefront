import { appEnv } from '@app/config/env';
import { IApiResponse } from '@app/lib/axios';
import { TOKEN_KEY } from '@app/lib/constants';
import {
  AgentData,
  AgentListData,
  AgentListResponse,
  AgentResponse,
  AgentStreamEvent,
  InferenceData,
  InferenceResponse,
} from '@app/types/agent';
import { VersionListData, VersionListResponse } from '@app/types/version';
import { consumeSSE } from '@app/utils/sse';
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

  /**
   * Run inference as a stream, calling `onEvent` for every frame.
   *
   * Uses fetch rather than the shared axios instance: XHR buffers the whole
   * response before handing it over, so nothing would arrive until the run
   * finished. That means re-doing what the axios interceptors give us for
   * free - the bearer token and the `:appId` substitution.
   *
   * The `Accept` header is load-bearing, not decoration: the console proxies
   * this call to floware and decides whether to stream based on it.
   */
  async streamInference(
    id: string,
    inputs: string | unknown[],
    variables: Record<string, unknown> = {},
    options: {
      version?: number;
      signal?: AbortSignal;
      onEvent: (event: AgentStreamEvent) => void;
    }
  ): Promise<void> {
    const appId = window.location.pathname.split('/')[2] ?? '';
    const query = options.version !== undefined ? `&version=${options.version}` : '';
    const url = `${appEnv.baseURL}/v1/${appId}/floware/v2/agents/${id}/inference?stream=true${query}`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        Authorization: `Bearer ${localStorage.getItem(TOKEN_KEY)}`,
        'Cache-Control': 'no-cache',
      },
      body: JSON.stringify({ variables, inputs, output_json_enabled: false }),
      signal: options.signal,
    });

    if (!response.ok) {
      throw new Error(await describeStreamFailure(response));
    }

    await consumeSSE(response, (data) => options.onEvent(data as AgentStreamEvent));
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

/**
 * The server's own message for a failed stream request, if it sent one.
 *
 * Everything that can fail deterministically - agent missing, model config
 * deleted - fails before the stream opens and comes back as the usual error
 * envelope, so it is worth reading rather than reporting a bare status.
 */
async function describeStreamFailure(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const message = body?.meta?.error;
    if (message) return message;
  } catch {
    // Not JSON; fall through to the status-based message.
  }

  if (response.status === 401) return 'Authentication failed. Please login again.';
  if (response.status === 403) return 'Access denied. Check your permissions.';
  if (response.status === 404) return 'Agent not found.';
  if (response.status >= 500) return 'Server error. Please try again later.';
  return `Streaming failed with status ${response.status}`;
}
