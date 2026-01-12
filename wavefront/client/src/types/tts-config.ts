import { IApiResponse } from '@app/lib/axios';

export type TtsProvider = 'elevenlabs' | 'deepgram' | 'cartesia';

export interface TtsConfig {
  id: string;
  display_name: string;
  description: string | null;
  provider: TtsProvider;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateTtsConfigRequest {
  display_name: string;
  description?: string | null;
  provider: TtsProvider;
  api_key: string;
}

export interface UpdateTtsConfigRequest {
  display_name?: string;
  description?: string | null;
  api_key?: string;
}

export interface TtsConfigData {
  message: string;
  tts_config_id: string;
}

export interface TtsConfigListData {
  tts_configs: TtsConfig[];
}

export type TtsConfigResponse = IApiResponse<TtsConfigData>;
export type TtsConfigDetailResponse = IApiResponse<TtsConfig>;
export type TtsConfigListResponse = IApiResponse<TtsConfigListData>;

// ElevenLabs specific parameters
export interface ElevenLabsParameters {
  model?: string; // default: 'eleven_turbo_v2_5'
  language?: string; // Language enum
  stability?: number; // 0-1
  similarity_boost?: number; // 0-1
  style?: number; // 0-1
  use_speaker_boost?: boolean;
  speed?: number; // 0.25-4.0
}

// Deepgram TTS specific parameters
export interface DeepgramTtsParameters {
  base_url?: string;
  encoding?: string;
  sample_rate?: number;
}

// Cartesia specific parameters
export interface CartesiaParameters {
  model?: string; // default: 'sonic-2'
  language?: string; // Language enum
  speed?: number;
}
