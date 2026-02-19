import { IApiResponse } from '@app/lib/axios';

export type SttProvider = 'deepgram' | 'sarvam' | 'elevenlabs';

export interface SttConfig {
  id: string;
  display_name: string;
  description: string | null;
  provider: SttProvider;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateSttConfigRequest {
  display_name: string;
  description?: string | null;
  provider: SttProvider;
  api_key: string;
}

export interface UpdateSttConfigRequest {
  display_name?: string;
  description?: string | null;
  api_key?: string;
}

export interface SttConfigData {
  message: string;
  stt_config_id: string;
}

export interface SttConfigListData {
  stt_configs: SttConfig[];
}

export type SttConfigResponse = IApiResponse<SttConfigData>;
export type SttConfigDetailResponse = IApiResponse<SttConfig>;
export type SttConfigListResponse = IApiResponse<SttConfigListData>;

// Deepgram STT specific parameters
export interface DeepgramSttParameters {
  model?: string; // default: 'nova-2'
  language?: string;
  interim_results?: boolean; // default: true
  encoding?: string; // default: 'linear16'
  sample_rate?: number; // default: 8000
  endpointing?: number; // milliseconds, default: 300
  channels?: number;
  smart_format?: boolean;
  punctuate?: boolean;
  profanity_filter?: boolean;
  vad_events?: boolean;
}

// Sarvam STT specific parameters
export interface SarvamSttParameters {
  model?: string; // default: 'saarika:v2.5'
  language?: string;
  vad_signals?: boolean;
  high_vad_sensitivity?: boolean;
}

// ElevenLabs STT specific parameters
export interface ElevenLabsSttParameters {
  model?: string; // default: 'scribe_v2_realtime'
  language?: string; // ISO-639-1 code e.g. 'en', 'hi'
  sample_rate?: number; // default: 8000
}
