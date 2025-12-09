import { IApiResponse } from "@app/lib/axios";

export type InferenceEngineType =
  | "gemini"
  | "openai"
  | "ollama"
  | "vllm"
  | "anthropic"
  | "azure_openai"
  | "groq";

export interface LLMInferenceConfig {
  id: string;
  llm_model: string;
  display_name: string;
  type: InferenceEngineType;
  base_url?: string;
  parameters?: Record<string, any> | null;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateLLMConfigRequest {
  llm_model: string;
  display_name: string;
  api_key?: string;
  type: InferenceEngineType;
  base_url?: string;
  parameters?: Record<string, any> | null;
}

export interface UpdateLLMConfigRequest {
  llm_model?: string;
  display_name?: string;
  api_key?: string | null;
  type?: InferenceEngineType;
  base_url?: string | null;
  parameters?: Record<string, any> | null;
}

export interface LLMConfigListData {
  configs: LLMInferenceConfig[];
}

export type LLMConfigResponse = IApiResponse<LLMInferenceConfig>;
export type LLMConfigListResponse = IApiResponse<LLMConfigListData>;
