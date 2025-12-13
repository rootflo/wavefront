import { IApiResponse } from '@app/lib/axios';

/**
 * Voice Agent entity interface
 */
export interface VoiceAgent {
  id: string;
  name: string;
  description: string | null;
  llm_config_id: string;
  tts_config_id: string;
  stt_config_id: string;
  telephony_config_id: string;
  system_prompt: string;
  welcome_message: string;
  conversation_config: Record<string, any> | null;
  status: 'active' | 'inactive';
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
}

/**
 * Request payload for creating a new voice agent
 */
export interface CreateVoiceAgentRequest {
  name: string;
  description?: string | null;
  llm_config_id: string;
  tts_config_id: string;
  stt_config_id: string;
  telephony_config_id: string;
  system_prompt: string;
  welcome_message: string;
  conversation_config?: Record<string, any> | null;
  status?: 'active' | 'inactive';
}

/**
 * Request payload for updating an existing voice agent
 * All fields are optional for partial updates
 */
export interface UpdateVoiceAgentRequest {
  name?: string;
  description?: string | null;
  llm_config_id?: string;
  tts_config_id?: string;
  stt_config_id?: string;
  telephony_config_id?: string;
  system_prompt?: string;
  welcome_message?: string;
  conversation_config?: Record<string, any> | null;
  status?: 'active' | 'inactive';
}

/**
 * Response data for create/update/delete operations
 */
export interface VoiceAgentData {
  message: string;
  voice_agent?: VoiceAgent;
  voice_agent_id?: string;
}

/**
 * Response data for list operations
 */
export interface VoiceAgentListData {
  voice_agents: VoiceAgent[];
}

/**
 * Response types using IApiResponse wrapper
 */
export type VoiceAgentResponse = IApiResponse<VoiceAgentData>;
export type VoiceAgentDetailResponse = IApiResponse<VoiceAgent>;
export type VoiceAgentListResponse = IApiResponse<VoiceAgentListData>;
