import { IApiResponse } from '@app/lib/axios';

/**
 * Chatbot entity interface
 */
export interface Chatbot {
  id: string;
  namespace: string;
  name: string;
  description: string | null;
  /** `null` for an agent-backed chatbot, which takes its prompt from the agent. */
  system_prompt: string | null;
  welcome_message: string | null;
  /** `null` for an agent-backed chatbot, which takes its model from the agent. */
  llm_config_id: string | null;
  /**
   * Set when the chatbot is backed by an agent: the agent supplies the prompt,
   * the model and the tools, and `system_prompt` and `llm_config_id` are `null`.
   */
  agent_id: string | null;
  /** A pinned agent version; `null` follows the agent's current version. */
  agent_version: number | null;
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
  /** With `llm_config_id`, for a direct LLM chatbot. Left out for an agent-backed one. */
  system_prompt?: string;
  welcome_message?: string | null;
  llm_config_id?: string;
  /** For an agent-backed chatbot: the agent supplies the prompt, model and tools. */
  agent_id?: string;
  /** Pin an agent version; left out follows the agent's current version. */
  agent_version?: number;
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
  /** Only for an agent-backed chatbot. A chatbot cannot change kind. */
  agent_id?: string;
  agent_version?: number;
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
