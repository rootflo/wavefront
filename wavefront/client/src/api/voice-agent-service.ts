import { IApiResponse } from '@app/lib/axios';
import {
  CreateVoiceAgentRequest,
  UpdateVoiceAgentRequest,
  VoiceAgent,
  VoiceAgentData,
  VoiceAgentDetailResponse,
  VoiceAgentListData,
  VoiceAgentListResponse,
  VoiceAgentResponse,
} from '@app/types/voice-agent';
import { AxiosInstance } from 'axios';

export class VoiceAgentService {
  constructor(private http: AxiosInstance) {}

  async createVoiceAgent(data: CreateVoiceAgentRequest): Promise<VoiceAgentResponse> {
    const response: IApiResponse<VoiceAgentData> = await this.http.post(`/v1/:appId/floware/v1/voice-agents`, data);
    return response;
  }

  async getVoiceAgent(agentId: string): Promise<VoiceAgentDetailResponse> {
    const response: IApiResponse<VoiceAgent> = await this.http.get(`/v1/:appId/floware/v1/voice-agents/${agentId}`);
    return response;
  }

  async updateVoiceAgent(agentId: string, data: UpdateVoiceAgentRequest): Promise<VoiceAgentResponse> {
    const response: IApiResponse<VoiceAgentData> = await this.http.patch(
      `/v1/:appId/floware/v1/voice-agents/${agentId}`,
      data
    );
    return response;
  }

  async deleteVoiceAgent(agentId: string): Promise<VoiceAgentResponse> {
    const response: IApiResponse<VoiceAgentData> = await this.http.delete(
      `/v1/:appId/floware/v1/voice-agents/${agentId}`
    );
    return response;
  }

  async listAllVoiceAgents(): Promise<VoiceAgentListResponse> {
    const response: IApiResponse<VoiceAgentListData> = await this.http.get(`/v1/:appId/floware/v1/voice-agents`);
    return response;
  }

  async initiateCall(agentId: string, data: { to_number: string; from_number?: string }): Promise<any> {
    const response = await this.http.post(`/v1/:appId/floware/v1/voice-agents/${agentId}/initiate`, data);
    return response;
  }
}
