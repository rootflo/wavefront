import { IApiResponse } from '@app/lib/axios';
import {
  CreateVoiceAgentRequest,
  CreateVoiceAgentRoomRequest,
  UpdateVoiceAgentRequest,
  VoiceAgent,
  VoiceAgentData,
  VoiceAgentDetailResponse,
  VoiceAgentListData,
  VoiceAgentListResponse,
  VoiceAgentResponse,
  VoiceAgentRoom,
  VoiceAgentRoomResponse,
} from '@app/types/voice-agent';
import { AxiosInstance } from 'axios';

export class VoiceAgentService {
  constructor(private http: AxiosInstance) {}

  async createVoiceAgent(data: CreateVoiceAgentRequest): Promise<VoiceAgentResponse> {
    const response: IApiResponse<VoiceAgentData> = await this.http.post(`/v1/:appId/floware/v1/voice-agents`, data);
    return response;
  }

  /** Full agent detail (prompts, config IDs, TTS/STT params). Use before edit or operations. */
  async getVoiceAgent(agentId: string): Promise<VoiceAgentDetailResponse> {
    const response: IApiResponse<VoiceAgent> = await this.http.get(
      `/v1/:appId/floware/v1/voice-agents/${agentId}/details`
    );
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

  async initiateCall(
    agentId: string,
    data: { to_number: string; from_number?: string }
  ): Promise<IApiResponse<unknown>> {
    const response = await this.http.post(`/v1/:appId/floware/v1/voice-agents/${agentId}/initiate`, data);
    return response;
  }

  /** Create a browser (WebRTC) room for an active voice agent. */
  async createRoom(agentId: string, options?: CreateVoiceAgentRoomRequest): Promise<VoiceAgentRoomResponse> {
    const response: IApiResponse<VoiceAgentRoom> = await this.http.post(
      `/v1/:appId/floware/v1/voice-agents/${agentId}/rooms`,
      options ?? {}
    );
    return response;
  }
}
