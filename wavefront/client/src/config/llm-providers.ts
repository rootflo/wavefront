/**
 * LLM Provider Configuration
 *
 * Every setting a provider can take, as the backends read it from a config's
 * `parameters`: call_processing (pipecat, llm_service.py) for voice agents and
 * flo_ai for chatbots and agents. Which of these a given model accepts lives
 * in llm-models.ts.
 *
 * Nothing is pre-filled: an unset setting is left out of the request, so the
 * provider's own default applies. `default` only documents that default (it
 * places the slider and labels the empty state).
 */

export type ParameterType = 'string' | 'number' | 'boolean' | 'select';

export interface ParameterOption {
  value: string | number;
  label: string;
}

export interface ParameterConfig {
  type: ParameterType;
  label: string;
  /** The provider's own default, for display only. */
  default?: unknown;
  min?: number;
  max?: number;
  step?: number;
  description?: string;
  placeholder?: string;
  options?: ParameterOption[];
  /** Shown under "Advanced" rather than with the everyday settings. */
  advanced?: boolean;
  /** The model takes this setting only while another setting has this value (e.g. temperature with reasoning effort None). */
  activeWhen?: { key: string; equals: string };
}

export interface ProviderConfig {
  name: string;
  baseUrl?: string;
  /** Voice agents (call_processing) can run this provider. */
  voiceSupported: boolean;
  /** What the model field holds for this provider. */
  modelLabel: string;
  modelHelp?: string;
  parameters: Record<string, ParameterConfig>;
}

/**
 * Select value for "no value chosen". Radix Select items cannot have an empty
 * value, so optional select parameters offer this item to clear the parameter.
 */
export const UNSET_SELECT_VALUE = '__unset__';

export type InferenceEngineType = 'gemini' | 'openai' | 'ollama' | 'vllm' | 'anthropic' | 'azure_openai' | 'groq';

const temperature = (max: number, description?: string): ParameterConfig => ({
  type: 'number',
  label: 'Temperature',
  default: 1,
  min: 0,
  max,
  step: 0.1,
  description: description ?? 'Higher is more varied, lower is more predictable',
});

const topP: ParameterConfig = {
  type: 'number',
  label: 'Top P',
  default: 1,
  min: 0,
  max: 1,
  step: 0.01,
  description: 'Nucleus sampling. Change this or temperature, not both',
  advanced: true,
};

const topK = (max: number): ParameterConfig => ({
  type: 'number',
  label: 'Top K',
  min: 1,
  max,
  step: 1,
  description: 'Sample only from the K most likely tokens',
  placeholder: '40',
  advanced: true,
});

const maxCompletionTokens = (max: number): ParameterConfig => ({
  type: 'number',
  label: 'Max output tokens',
  min: 1,
  max,
  step: 1,
  description: 'Caps the reply, reasoning tokens included. Voice replies rarely need more than 300',
  placeholder: 'No limit',
});

const maxTokens = (max: number, placeholder = 'No limit'): ParameterConfig => ({
  type: 'number',
  label: 'Max output tokens',
  min: 1,
  max,
  step: 1,
  description: 'Caps the length of the reply',
  placeholder,
});

const penalty = (label: string, description: string): ParameterConfig => ({
  type: 'number',
  label,
  default: 0,
  min: -2,
  max: 2,
  step: 0.1,
  description,
  advanced: true,
});

const seed: ParameterConfig = {
  type: 'number',
  label: 'Seed',
  min: 0,
  max: 999999,
  step: 1,
  description: 'Best-effort repeatable outputs for the same input',
  placeholder: 'Random',
  advanced: true,
};

const serviceTier: ParameterConfig = {
  type: 'select',
  label: 'Service tier',
  description: 'Request routing tier',
  options: [
    { value: 'auto', label: 'Auto' },
    { value: 'default', label: 'Default' },
  ],
  advanced: true,
};

/** Every effort value any OpenAI-family model takes; llm-models.ts narrows it per model. */
const reasoningEffort: ParameterConfig = {
  type: 'select',
  label: 'Reasoning effort',
  description: 'How long the model thinks before answering. Lower is faster; voice agents should use the lowest',
  options: [
    { value: 'none', label: 'None' },
    { value: 'minimal', label: 'Minimal' },
    { value: 'low', label: 'Low' },
    { value: 'medium', label: 'Medium' },
    { value: 'high', label: 'High' },
    { value: 'xhigh', label: 'Extra high' },
  ],
};

const thinkingLevel: ParameterConfig = {
  type: 'select',
  label: 'Thinking level',
  description: 'How long Gemini thinks before answering. Lower is faster',
  options: [
    { value: 'minimal', label: 'Minimal' },
    { value: 'low', label: 'Low' },
    { value: 'medium', label: 'Medium' },
    { value: 'high', label: 'High' },
  ],
};

const thinkingBudget: ParameterConfig = {
  type: 'number',
  label: 'Thinking budget',
  min: 0,
  max: 24576,
  step: 128,
  description: 'Tokens Gemini may spend thinking. 0 turns thinking off where the model allows it',
  placeholder: 'Model decides',
};

const frequencyPenalty = penalty('Frequency penalty', 'Discourages repeating the same words');
const presencePenalty = penalty('Presence penalty', 'Encourages moving on to new topics');

export const LLM_PROVIDERS_CONFIG: Record<InferenceEngineType, ProviderConfig> = {
  openai: {
    name: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    voiceSupported: true,
    modelLabel: 'Model',
    modelHelp: 'Pick a model, or type any model ID. A non-OpenAI base URL makes this an OpenAI-compatible endpoint',
    parameters: {
      reasoning_effort: reasoningEffort,
      temperature: temperature(2),
      max_completion_tokens: maxCompletionTokens(128000),
      top_p: topP,
      frequency_penalty: frequencyPenalty,
      presence_penalty: presencePenalty,
      seed,
      service_tier: serviceTier,
    },
  },
  azure_openai: {
    name: 'Azure OpenAI',
    voiceSupported: true,
    modelLabel: 'Deployment name',
    modelHelp:
      'The name of your Azure deployment. Picking a model fills it in; settings are matched from the name, so deployments named after their model get the right ones',
    parameters: {
      reasoning_effort: reasoningEffort,
      temperature: temperature(2),
      max_completion_tokens: maxCompletionTokens(128000),
      top_p: topP,
      frequency_penalty: frequencyPenalty,
      presence_penalty: presencePenalty,
      seed,
    },
  },
  gemini: {
    name: 'Google Gemini',
    baseUrl: 'https://generativelanguage.googleapis.com',
    voiceSupported: true,
    modelLabel: 'Model',
    parameters: {
      thinking_level: thinkingLevel,
      thinking_budget: thinkingBudget,
      temperature: temperature(2, 'Google recommends leaving Gemini 3 models at the default (1.0)'),
      max_tokens: maxTokens(65536),
      top_p: topP,
      top_k: topK(100),
    },
  },
  groq: {
    name: 'Groq',
    baseUrl: 'https://api.groq.com/openai/v1',
    voiceSupported: true,
    modelLabel: 'Model',
    parameters: {
      reasoning_effort: { ...reasoningEffort, options: reasoningEffort.options?.filter((o) => o.value !== 'none') },
      temperature: temperature(2),
      max_completion_tokens: maxCompletionTokens(65536),
      top_p: topP,
      frequency_penalty: frequencyPenalty,
      presence_penalty: presencePenalty,
      seed,
      service_tier: serviceTier,
    },
  },
  anthropic: {
    name: 'Anthropic Claude',
    baseUrl: 'https://api.anthropic.com',
    voiceSupported: false,
    modelLabel: 'Model',
    parameters: {
      temperature: temperature(1),
      max_tokens: maxTokens(128000, '1024'),
      top_p: topP,
      top_k: topK(500),
    },
  },
  ollama: {
    name: 'Ollama (Local)',
    voiceSupported: false,
    modelLabel: 'Model',
    modelHelp: 'A model pulled on your Ollama server, e.g. llama3.3',
    parameters: {
      temperature: temperature(2),
      max_tokens: maxTokens(32000),
      top_p: topP,
      top_k: topK(100),
    },
  },
  vllm: {
    name: 'vLLM',
    voiceSupported: false,
    modelLabel: 'Model',
    modelHelp: 'The model name your vLLM server serves',
    parameters: {
      temperature: temperature(2),
      max_tokens: maxTokens(32000),
      top_p: topP,
      top_k: { ...topK(100), min: -1, description: 'Sample only from the K most likely tokens (-1 to disable)' },
      frequency_penalty: frequencyPenalty,
      presence_penalty: presencePenalty,
    },
  },
};

export const INFERENCE_ENGINE_TYPES: InferenceEngineType[] = [
  'openai',
  'azure_openai',
  'gemini',
  'groq',
  'anthropic',
  'ollama',
  'vllm',
];

/**
 * Get provider configuration
 */
export function getProviderConfig(provider: InferenceEngineType): ProviderConfig | null {
  return LLM_PROVIDERS_CONFIG[provider] || null;
}

/**
 * Get default base URL for a provider
 */
export function getDefaultBaseUrl(provider: InferenceEngineType): string {
  const config = getProviderConfig(provider);
  return config?.baseUrl || '';
}
