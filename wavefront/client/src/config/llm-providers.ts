/**
 * LLM Provider Configuration
 *
 * Centralized configuration for LLM inference providers.
 * Based on pipecat implementation (pipecat/llm-service.py)
 */

export type ParameterType = 'string' | 'number' | 'boolean' | 'select';

export interface ParameterConfig {
  type: ParameterType;
  default: any;
  min?: number;
  max?: number;
  step?: number;
  description?: string;
  placeholder?: string;
  options?: Array<{ value: string | number; label: string }>;
}

export interface ProviderConfig {
  name: string;
  badge: {
    bg: string;
    text: string;
  };
  parameters: Record<string, ParameterConfig>;
}

export type InferenceEngineType = 'gemini' | 'openai' | 'ollama' | 'vllm' | 'anthropic' | 'azure_openai' | 'groq';

/**
 * LLM Provider Configuration
 * Parameters mapped from pipecat/llm-service.py implementation
 */
export const LLM_PROVIDERS_CONFIG: Record<InferenceEngineType, ProviderConfig> = {
  openai: {
    name: 'OpenAI GPT',
    badge: {
      bg: 'bg-green-100',
      text: 'text-green-800',
    },
    parameters: {
      temperature: {
        type: 'number',
        default: 0.7,
        min: 0,
        max: 2,
        step: 0.1,
        description: 'Controls randomness in responses (0-2)',
        placeholder: '0.7',
      },
      max_completion_tokens: {
        type: 'number',
        default: undefined,
        min: 1,
        max: 16000,
        step: 1,
        description: 'Maximum completion tokens',
        placeholder: '1000',
      },
      top_p: {
        type: 'number',
        default: 1.0,
        min: 0,
        max: 1,
        step: 0.01,
        description: 'Nucleus sampling threshold (0-1)',
        placeholder: '1.0',
      },
      frequency_penalty: {
        type: 'number',
        default: 0.0,
        min: -2,
        max: 2,
        step: 0.1,
        description: 'Penalize repeated tokens (-2 to 2)',
        placeholder: '0.0',
      },
      presence_penalty: {
        type: 'number',
        default: 0.0,
        min: -2,
        max: 2,
        step: 0.1,
        description: 'Penalize new topics (-2 to 2)',
        placeholder: '0.0',
      },
      seed: {
        type: 'number',
        default: undefined,
        min: 0,
        max: 999999,
        step: 1,
        description: 'Random seed for deterministic outputs',
        placeholder: '42',
      },
      service_tier: {
        type: 'select',
        default: undefined,
        description: 'Service tier for request routing',
        options: [
          { value: 'auto', label: 'Auto' },
          { value: 'default', label: 'Default' },
        ],
      },
    },
  },
  anthropic: {
    name: 'Anthropic Claude',
    badge: {
      bg: 'bg-orange-100',
      text: 'text-orange-800',
    },
    parameters: {
      temperature: {
        type: 'number',
        default: 0.7,
        min: 0,
        max: 1,
        step: 0.1,
        description: 'Controls randomness in responses (0-1)',
        placeholder: '0.7',
      },
      max_tokens: {
        type: 'number',
        default: 1024,
        min: 1,
        max: 8192,
        step: 1,
        description: 'Maximum number of tokens to generate',
        placeholder: '1024',
      },
      top_p: {
        type: 'number',
        default: 1.0,
        min: 0,
        max: 1,
        step: 0.01,
        description: 'Nucleus sampling threshold (0-1)',
        placeholder: '1.0',
      },
      top_k: {
        type: 'number',
        default: undefined,
        min: 1,
        max: 500,
        step: 1,
        description: 'Top-K sampling parameter',
        placeholder: '40',
      },
    },
  },
  gemini: {
    name: 'Google Gemini',
    badge: {
      bg: 'bg-blue-100',
      text: 'text-blue-800',
    },
    parameters: {
      temperature: {
        type: 'number',
        default: 0.7,
        min: 0,
        max: 2,
        step: 0.1,
        description: 'Controls randomness in responses (0-2)',
        placeholder: '0.7',
      },
      max_tokens: {
        type: 'number',
        default: 1024,
        min: 1,
        max: 8192,
        step: 1,
        description: 'Maximum output tokens',
        placeholder: '1024',
      },
      top_p: {
        type: 'number',
        default: 0.95,
        min: 0,
        max: 1,
        step: 0.01,
        description: 'Nucleus sampling threshold (0-1)',
        placeholder: '0.95',
      },
      top_k: {
        type: 'number',
        default: 40,
        min: 1,
        max: 100,
        step: 1,
        description: 'Top-K sampling parameter',
        placeholder: '40',
      },
    },
  },
  azure_openai: {
    name: 'Azure OpenAI',
    badge: {
      bg: 'bg-cyan-100',
      text: 'text-cyan-800',
    },
    parameters: {
      temperature: {
        type: 'number',
        default: 0.7,
        min: 0,
        max: 2,
        step: 0.1,
        description: 'Controls randomness in responses (0-2)',
        placeholder: '0.7',
      },
      max_completion_tokens: {
        type: 'number',
        default: undefined,
        min: 1,
        max: 16000,
        step: 1,
        description: 'Maximum completion tokens',
        placeholder: '1000',
      },
      top_p: {
        type: 'number',
        default: 1.0,
        min: 0,
        max: 1,
        step: 0.01,
        description: 'Nucleus sampling threshold (0-1)',
        placeholder: '1.0',
      },
      frequency_penalty: {
        type: 'number',
        default: 0.0,
        min: -2,
        max: 2,
        step: 0.1,
        description: 'Penalize repeated tokens (-2 to 2)',
        placeholder: '0.0',
      },
      presence_penalty: {
        type: 'number',
        default: 0.0,
        min: -2,
        max: 2,
        step: 0.1,
        description: 'Penalize new topics (-2 to 2)',
        placeholder: '0.0',
      },
      seed: {
        type: 'number',
        default: undefined,
        min: 0,
        max: 999999,
        step: 1,
        description: 'Random seed for deterministic outputs',
        placeholder: '42',
      },
    },
  },
  groq: {
    name: 'Groq',
    badge: {
      bg: 'bg-purple-100',
      text: 'text-purple-800',
    },
    parameters: {
      temperature: {
        type: 'number',
        default: 0.7,
        min: 0,
        max: 2,
        step: 0.1,
        description: 'Controls randomness in responses (0-2)',
        placeholder: '0.7',
      },
      max_completion_tokens: {
        type: 'number',
        default: undefined,
        min: 1,
        max: 8000,
        step: 1,
        description: 'Maximum completion tokens',
        placeholder: '1000',
      },
      top_p: {
        type: 'number',
        default: 1.0,
        min: 0,
        max: 1,
        step: 0.01,
        description: 'Nucleus sampling threshold (0-1)',
        placeholder: '1.0',
      },
      frequency_penalty: {
        type: 'number',
        default: 0.0,
        min: -2,
        max: 2,
        step: 0.1,
        description: 'Penalize repeated tokens (-2 to 2)',
        placeholder: '0.0',
      },
      presence_penalty: {
        type: 'number',
        default: 0.0,
        min: -2,
        max: 2,
        step: 0.1,
        description: 'Penalize new topics (-2 to 2)',
        placeholder: '0.0',
      },
      seed: {
        type: 'number',
        default: undefined,
        min: 0,
        max: 999999,
        step: 1,
        description: 'Random seed for deterministic outputs',
        placeholder: '42',
      },
      service_tier: {
        type: 'select',
        default: undefined,
        description: 'Service tier for request routing',
        options: [
          { value: 'auto', label: 'Auto' },
          { value: 'default', label: 'Default' },
        ],
      },
    },
  },
  ollama: {
    name: 'Ollama (Local)',
    badge: {
      bg: 'bg-gray-100',
      text: 'text-gray-800',
    },
    parameters: {
      temperature: {
        type: 'number',
        default: 0.7,
        min: 0,
        max: 2,
        step: 0.1,
        description: 'Controls randomness in responses (0-2)',
        placeholder: '0.7',
      },
      max_tokens: {
        type: 'number',
        default: 150,
        min: 1,
        max: 32000,
        step: 1,
        description: 'Maximum number of tokens to generate',
        placeholder: '150',
      },
      top_p: {
        type: 'number',
        default: 1.0,
        min: 0,
        max: 1,
        step: 0.01,
        description: 'Nucleus sampling threshold (0-1)',
        placeholder: '1.0',
      },
      top_k: {
        type: 'number',
        default: 40,
        min: 1,
        max: 100,
        step: 1,
        description: 'Top-K sampling parameter',
        placeholder: '40',
      },
    },
  },
  vllm: {
    name: 'vLLM',
    badge: {
      bg: 'bg-indigo-100',
      text: 'text-indigo-800',
    },
    parameters: {
      temperature: {
        type: 'number',
        default: 0.7,
        min: 0,
        max: 2,
        step: 0.1,
        description: 'Controls randomness in responses (0-2)',
        placeholder: '0.7',
      },
      max_tokens: {
        type: 'number',
        default: 150,
        min: 1,
        max: 32000,
        step: 1,
        description: 'Maximum number of tokens to generate',
        placeholder: '150',
      },
      top_p: {
        type: 'number',
        default: 1.0,
        min: 0,
        max: 1,
        step: 0.01,
        description: 'Nucleus sampling threshold (0-1)',
        placeholder: '1.0',
      },
      top_k: {
        type: 'number',
        default: -1,
        min: -1,
        max: 100,
        step: 1,
        description: 'Top-K sampling parameter (-1 to disable)',
        placeholder: '-1',
      },
      frequency_penalty: {
        type: 'number',
        default: 0.0,
        min: -2,
        max: 2,
        step: 0.1,
        description: 'Penalize repeated tokens (-2 to 2)',
        placeholder: '0.0',
      },
      presence_penalty: {
        type: 'number',
        default: 0.0,
        min: -2,
        max: 2,
        step: 0.1,
        description: 'Penalize new topics (-2 to 2)',
        placeholder: '0.0',
      },
    },
  },
};

/**
 * Get provider configuration
 */
export function getProviderConfig(provider: InferenceEngineType): ProviderConfig | null {
  return LLM_PROVIDERS_CONFIG[provider] || null;
}

/**
 * Get provider badge
 */
export function getProviderBadge(provider: InferenceEngineType): { bg: string; text: string } {
  const config = LLM_PROVIDERS_CONFIG[provider];
  return config ? config.badge : { bg: 'bg-gray-100', text: 'text-gray-800' };
}

/**
 * Initialize parameters with defaults for a provider
 */
export function initializeParameters(provider: InferenceEngineType): Record<string, any> {
  const config = getProviderConfig(provider);
  if (!config) return {};

  const params: Record<string, any> = {};
  Object.entries(config.parameters).forEach(([key, paramConfig]) => {
    // Only include parameters with defined defaults
    if (paramConfig.default !== undefined) {
      params[key] = paramConfig.default;
    }
  });

  return params;
}

/**
 * Merge saved parameters with defaults (for edit mode)
 * Prioritizes saved values over defaults
 */
export function mergeParameters(
  provider: InferenceEngineType,
  savedParams: Record<string, any> | null | undefined
): Record<string, any> {
  const defaultParams = initializeParameters(provider);

  if (!savedParams) return defaultParams;

  // Override defaults with saved values, removing undefined/null values
  const merged = { ...defaultParams };
  Object.entries(savedParams).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      merged[key] = value;
    }
  });

  return merged;
}

/**
 * Clean parameters by removing undefined, null, and empty string values
 */
export function cleanParameters(params: Record<string, any>): Record<string, any> {
  const cleaned: Record<string, any> = {};
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      cleaned[key] = value;
    }
  });
  return cleaned;
}
