import { IApiResponse } from '@app/lib/axios';
import {
  VoiceAgentTool,
  CreateToolRequest,
  UpdateToolRequest,
  AttachToolToAgentRequest,
  UpdateAgentToolRequest,
  ListToolsParams,
  ToolResponse,
  ToolDetailResponse,
  ToolListResponse,
  AgentToolsResponse,
  ToolListData,
  AgentToolsData,
  ToolData,
} from '@app/types/tool';
import { AxiosInstance } from 'axios';

export class ToolService {
  constructor(private http: AxiosInstance) {}

  /**
   * Create a new tool
   */
  async createTool(data: CreateToolRequest): Promise<ToolResponse> {
    const response: IApiResponse<ToolData> = await this.http.post(`/v1/:appId/floware/v1/tools`, data);
    return response;
  }

  /**
   * Get a single tool by ID
   */
  async getTool(toolId: string): Promise<ToolDetailResponse> {
    const response: IApiResponse<VoiceAgentTool> = await this.http.get(`/v1/:appId/floware/v1/tools/${toolId}`);
    return response;
  }

  /**
   * List all tools with optional filters
   */
  async listTools(params?: ListToolsParams): Promise<ToolListResponse> {
    const response: IApiResponse<ToolListData> = await this.http.get(`/v1/:appId/floware/v1/tools`, { params });
    return response;
  }

  /**
   * Get tool names and details
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getToolNamesAndDetails(): Promise<any> {
    const response = await this.http.get(`/v1/:appId/floware/v1/tools/names`);
    return response;
  }

  /**
   * Update an existing tool
   */
  async updateTool(toolId: string, data: UpdateToolRequest): Promise<ToolResponse> {
    const response: IApiResponse<ToolData> = await this.http.patch(`/v1/:appId/floware/v1/tools/${toolId}`, data);
    return response;
  }

  /**
   * Delete a tool (soft delete)
   */
  async deleteTool(toolId: string): Promise<ToolResponse> {
    const response: IApiResponse<ToolData> = await this.http.delete(`/v1/:appId/floware/v1/tools/${toolId}`);
    return response;
  }

  /**
   * Attach a tool to a voice agent
   */
  async attachToolToAgent(agentId: string, data: AttachToolToAgentRequest): Promise<ToolResponse> {
    const response: IApiResponse<ToolData> = await this.http.post(
      `/v1/:appId/floware/v1/voice-agents/${agentId}/tools`,
      data
    );
    return response;
  }

  /**
   * Get all tools attached to a voice agent
   */
  async getAgentTools(agentId: string): Promise<AgentToolsResponse> {
    const response: IApiResponse<AgentToolsData> = await this.http.get(
      `/v1/:appId/floware/v1/voice-agents/${agentId}/tools`
    );
    return response;
  }

  /**
   * Update a tool association for a voice agent
   */
  async updateAgentTool(agentId: string, toolId: string, data: UpdateAgentToolRequest): Promise<ToolResponse> {
    const response: IApiResponse<ToolData> = await this.http.patch(
      `/v1/:appId/floware/v1/voice-agents/${agentId}/tools/${toolId}`,
      data
    );
    return response;
  }

  /**
   * Detach a tool from a voice agent
   */
  async detachToolFromAgent(agentId: string, toolId: string): Promise<ToolResponse> {
    const response: IApiResponse<ToolData> = await this.http.delete(
      `/v1/:appId/floware/v1/voice-agents/${agentId}/tools/${toolId}`
    );
    return response;
  }
}
