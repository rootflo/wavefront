import { IApiResponse } from '@app/lib/axios';

/**
 * Chatbot entity interface
 */
export interface Chatbot {
  id: string;
  namespace: string;
  name: string;
  description: string | null;
  system_prompt: string;
  welcome_message: string | null;
  llm_config_id: string;
  /**
   * Overrides on top of the LLM config. Only `temperature` is honoured today.
   * `null` means "use the model's own settings".
   *
   * Read `temperature` by key presence, never truthiness -- 0 is a valid
   * setting and is falsy.
   */
  config: Record<string, unknown> | null;
  enabled: boolean;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
}

/**
 * Request payload for creating a new chatbot
 */
export interface CreateChatbotRequest {
  name: string;
  namespace?: string;
  description?: string | null;
  system_prompt: string;
  welcome_message?: string | null;
  llm_config_id: string;
  config?: Record<string, unknown> | null;
  enabled?: boolean;
}

/**
 * Request payload for updating an existing chatbot.
 *
 * `namespace` is absent on purpose -- the API does not accept it, so a
 * chatbot's namespace is fixed at creation.
 *
 * The API reads `null` as "not supplied" rather than "set to null", so always
 * send a concrete value: `''` clears a description or welcome message, `{}`
 * clears the config.
 */
export interface UpdateChatbotRequest {
  name?: string;
  description?: string | null;
  system_prompt?: string;
  welcome_message?: string | null;
  llm_config_id?: string;
  config?: Record<string, unknown> | null;
  enabled?: boolean;
}

export interface ChatbotListData {
  chatbots: Chatbot[];
}

export interface ChatbotData {
  message: string;
  chatbot: Chatbot;
}

export type ChatbotResponse = IApiResponse<ChatbotData>;
export type ChatbotDetailResponse = IApiResponse<{ chatbot: Chatbot }>;
export type ChatbotListResponse = IApiResponse<ChatbotListData>;
export type ChatbotDeleteResponse = IApiResponse<{ message: string }>;
