import { IApiResponse } from '@app/lib/axios';

/**
 * Compact voice agent fields for table / list views.
 * Full prompts, params, and config IDs are omitted — fetch VoiceAgent for those.
 */
export interface VoiceAgentListItem {
  id: string;
  name: string;
  description: string | null;
  status: 'active' | 'inactive';
  supported_languages: string[];
  default_language: string;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
}

/**
 * Full voice agent entity (edit / operations / runtime).
 */
export interface VoiceAgent extends VoiceAgentListItem {
  llm_config_id: string;
  tts_config_id: string;
  stt_config_id: string;
  telephony_config_id: string;
  system_prompt: string;
  welcome_message: string;
  tts_voice_ids: Record<string, string>;
  tts_parameters: Record<string, unknown> | null;
  stt_parameters: Record<string, unknown> | null;
  conversation_config: Record<string, unknown> | null;
  inbound_numbers: string[];
  outbound_numbers: string[];
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
  tts_voice_ids: Record<string, string>;
  tts_parameters?: Record<string, unknown> | null;
  stt_parameters?: Record<string, unknown> | null;
  conversation_config?: Record<string, unknown> | null;
  status?: 'active' | 'inactive';
  inbound_numbers?: string[];
  outbound_numbers?: string[];
  supported_languages?: string[];
  default_language?: string;
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
  tts_voice_ids?: Record<string, string>;
  tts_parameters?: Record<string, unknown> | null;
  stt_parameters?: Record<string, unknown> | null;
  conversation_config?: Record<string, unknown> | null;
  status?: 'active' | 'inactive';
  inbound_numbers?: string[];
  outbound_numbers?: string[];
  supported_languages?: string[];
  default_language?: string;
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
  voice_agents: VoiceAgentListItem[];
}

/**
 * Response types using IApiResponse wrapper
 */
export type VoiceAgentResponse = IApiResponse<VoiceAgentData>;
export type VoiceAgentDetailResponse = IApiResponse<VoiceAgent>;
export type VoiceAgentListResponse = IApiResponse<VoiceAgentListData>;

/**
 * Browser (WebRTC) voice room. `join_token` is one-time: it is shown once and the
 * browser sends it with its SDP offer.
 */
export interface VoiceAgentRoom {
  room_id: string;
  voice_agent_id: string;
  join_token: string;
  /** Base URL of the signaling API (the browser POSTs `${signaling_url}/offer`). */
  signaling_url: string;
  /** True when `signaling_url` is a floware-relative path proxied to call_processing. */
  signaling_via_floware?: boolean;
  /**
   * Agents this room can run (the initial agent first). The server enforces the same list, so these are
   * the only agents the browser may hot-swap to mid-session.
   */
  agents?: VoiceAgentRoomAgent[];
}

export interface VoiceAgentRoomAgent {
  id: string;
  name: string;
}

export type VoiceAgentRoomResponse = IApiResponse<VoiceAgentRoom>;

/** Options for creating a browser (WebRTC) room — mirrors CreateWebRTCRoomPayload. */
export interface CreateVoiceAgentRoomRequest {
  /** Narrow hot-swap allowlist to these active agents (initial agent always included). Omit for all active. */
  allowed_agent_ids?: string[];
  /**
   * When true, the app drives language via room context (set_context.language);
   * agent language-switching rules/tool are disabled. Default false.
   */
  room_context_handles_language?: boolean;
  /**
   * When swapping agents, carry conversation history to the new agent. Default true.
   */
  carry_history_on_swap?: boolean;
}
