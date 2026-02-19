/**
 * Voice Provider Configuration
 *
 * Centralized configuration for TTS and STT providers.
 * Based on pipecat implementation (pipecat/tts-service.py and pipecat/stt-service.py)
 */

export type ParameterType = 'string' | 'number' | 'boolean' | 'array';

export interface ParameterConfig {
  type: ParameterType;
  default: unknown;
  min?: number;
  max?: number;
  step?: number;
  description?: string;
  placeholder?: string;
  options?: string[] | number[]; // For select/dropdown - supports string and number types
}

export interface ProviderConfig {
  name: string;
  badge: {
    bg: string;
    text: string;
  };
  parameters: Record<string, ParameterConfig>;
}

export interface VoiceProvidersConfig {
  tts: {
    providers: readonly string[];
    configs: Record<string, ProviderConfig>;
  };
  stt: {
    providers: readonly string[];
    configs: Record<string, ProviderConfig>;
  };
}

/**
 * Voice Providers Configuration
 * Only includes providers actually implemented in pipecat
 */
export const VOICE_PROVIDERS_CONFIG: VoiceProvidersConfig = {
  tts: {
    providers: ['elevenlabs', 'deepgram', 'cartesia', 'sarvam'] as const,
    configs: {
      elevenlabs: {
        name: 'ElevenLabs',
        badge: {
          bg: 'bg-purple-100',
          text: 'text-purple-800',
        },
        parameters: {
          model: {
            type: 'string',
            default: 'eleven_turbo_v2_5',
            description: 'ElevenLabs model to use',
            placeholder: 'eleven_turbo_v2_5',
          },
          language: {
            type: 'string',
            default: '',
            description: 'Language code (e.g., en, es, fr)',
            placeholder: 'en',
          },
          stability: {
            type: 'number',
            default: 0.5,
            min: 0,
            max: 1,
            step: 0.05,
            description: 'Controls voice consistency (0-1)',
          },
          similarity_boost: {
            type: 'number',
            default: 0.75,
            min: 0,
            max: 1,
            step: 0.05,
            description: 'Enhances voice similarity (0-1)',
          },
          style: {
            type: 'number',
            default: 0.0,
            min: 0,
            max: 1,
            step: 0.05,
            description: 'Style exaggeration (0-1)',
          },
          use_speaker_boost: {
            type: 'boolean',
            default: true,
            description: 'Enable speaker boost for better clarity',
          },
          speed: {
            type: 'number',
            default: 1.0,
            min: 0.25,
            max: 4.0,
            step: 0.05,
            description: 'Speech speed (0.25-4.0)',
          },
        },
      },
      deepgram: {
        name: 'Deepgram',
        badge: {
          bg: 'bg-blue-100',
          text: 'text-blue-800',
        },
        parameters: {
          base_url: {
            type: 'string',
            default: '',
            description: 'Custom API endpoint (optional)',
            placeholder: 'https://api.deepgram.com',
          },
          encoding: {
            type: 'string',
            default: '',
            description: 'Audio encoding format',
            placeholder: 'linear16',
          },
          sample_rate: {
            type: 'number',
            default: undefined,
            description: 'Audio sample rate in Hz',
            placeholder: '16000',
          },
        },
      },
      cartesia: {
        name: 'Cartesia',
        badge: {
          bg: 'bg-green-100',
          text: 'text-green-800',
        },
        parameters: {
          model: {
            type: 'string',
            default: 'sonic-2',
            description: 'Cartesia model to use',
            placeholder: 'sonic-2',
          },
          language: {
            type: 'string',
            default: '',
            description: 'Language code (e.g., en, es, fr)',
            placeholder: 'en',
          },
          speed: {
            type: 'number',
            default: undefined,
            description: 'Speech speed multiplier',
            placeholder: '1.0',
            step: 0.1,
          },
        },
      },
      sarvam: {
        name: 'Sarvam',
        badge: {
          bg: 'bg-orange-100',
          text: 'text-orange-800',
        },
        parameters: {
          model: {
            type: 'string',
            default: 'bulbul:v2',
            options: ['bulbul:v2', 'bulbul:v3'],
            description: 'Sarvam TTS model',
          },
          language: {
            type: 'string',
            default: '',
            description: 'Language code',
            placeholder: 'hi',
          },
          pitch: {
            type: 'number',
            default: 0.0,
            min: -0.75,
            max: 0.75,
            step: 0.05,
            description: 'Voice pitch (-0.75 to 0.75)',
          },
          pace: {
            type: 'number',
            default: 1.0,
            min: 0.3,
            max: 3.0,
            step: 0.1,
            description: 'Speech pace (0.3-3.0)',
          },
          loudness: {
            type: 'number',
            default: 1.0,
            min: 0.1,
            max: 3.0,
            step: 0.1,
            description: 'Volume (0.1-3.0)',
          },
          enable_preprocessing: {
            type: 'boolean',
            default: false,
            description: 'Enable text preprocessing',
          },
          temperature: {
            type: 'number',
            default: 0.6,
            min: 0.01,
            max: 1.0,
            step: 0.05,
            description: 'Randomness for bulbul v3 (0.01-1.0)',
          },
        },
      },
    },
  },
  stt: {
    providers: ['deepgram', 'sarvam', 'elevenlabs'] as const,
    configs: {
      deepgram: {
        name: 'Deepgram',
        badge: {
          bg: 'bg-blue-100',
          text: 'text-blue-800',
        },
        parameters: {
          model: {
            type: 'string',
            default: 'nova-2',
            description: 'Deepgram STT model',
            options: ['nova-2', 'nova-3-general'],
          },
          language: {
            type: 'string',
            default: '',
            description: 'Language code (e.g., en-US, es-ES)',
            placeholder: 'en-US',
          },
          interim_results: {
            type: 'boolean',
            default: true,
            description: 'Enable interim results for faster feedback',
          },
          encoding: {
            type: 'string',
            default: 'linear16',
            description: 'Audio encoding format',
            placeholder: 'linear16',
          },
          sample_rate: {
            type: 'number',
            default: 8000,
            description: 'Audio sample rate in Hz',
            placeholder: '8000',
          },
          endpointing: {
            type: 'number',
            default: 300,
            min: 10,
            max: 2000,
            step: 10,
            description: 'Silence duration (ms) to detect end of speech',
          },
          channels: {
            type: 'number',
            default: undefined,
            description: 'Number of audio channels',
            placeholder: '1',
          },
          smart_format: {
            type: 'boolean',
            default: false,
            description: 'Enable automatic formatting',
          },
          punctuate: {
            type: 'boolean',
            default: false,
            description: 'Add punctuation to transcription',
          },
          profanity_filter: {
            type: 'boolean',
            default: false,
            description: 'Filter profanity from transcription',
          },
          vad_events: {
            type: 'boolean',
            default: false,
            description: 'Enable voice activity detection events',
          },
        },
      },
      sarvam: {
        name: 'Sarvam',
        badge: {
          bg: 'bg-orange-100',
          text: 'text-orange-800',
        },
        parameters: {
          model: {
            type: 'string',
            default: 'saarika:v2.5',
            options: ['saarika:v2.5', 'saaras:v2.5', 'saaras:v3'],
            description: 'Sarvam STT model',
          },
          language: {
            type: 'string',
            default: '',
            description: 'Language code',
            placeholder: 'hi',
          },
          vad_signals: {
            type: 'boolean',
            default: true,
            description: 'Enable VAD signals',
          },
          high_vad_sensitivity: {
            type: 'boolean',
            default: false,
            description: 'High VAD sensitivity',
          },
        },
      },
      elevenlabs: {
        name: 'ElevenLabs',
        badge: {
          bg: 'bg-purple-100',
          text: 'text-purple-800',
        },
        parameters: {
          model: {
            type: 'string',
            default: 'scribe_v2_realtime',
            description: 'ElevenLabs STT model',
            options: ['scribe_v2_realtime'],
          },
          language: {
            type: 'string',
            default: '',
            description: 'Language code (ISO-639-1, e.g., en, hi)',
            placeholder: 'en',
          },
          sample_rate: {
            type: 'number',
            default: 8000,
            description: 'Audio sample rate in Hz',
            placeholder: '8000',
          },
        },
      },
    },
  },
};

/**
 * Get provider configuration
 */
export function getProviderConfig(type: 'tts' | 'stt', provider: string): ProviderConfig | null {
  return VOICE_PROVIDERS_CONFIG[type].configs[provider] || null;
}

/**
 * Get all providers for a type
 */
export function getProviders(type: 'tts' | 'stt'): readonly string[] {
  return VOICE_PROVIDERS_CONFIG[type].providers;
}

/**
 * Initialize parameters with defaults for a provider
 */
export function initializeParameters(type: 'tts' | 'stt', provider: string): Record<string, unknown> {
  const config = getProviderConfig(type, provider);
  if (!config) return {};

  const params: Record<string, unknown> = {};
  Object.entries(config.parameters).forEach(([key, paramConfig]) => {
    params[key] = paramConfig.default;
  });

  return params;
}

/**
 * Merge saved parameters with defaults (for edit mode)
 */
export function mergeParameters(
  type: 'tts' | 'stt',
  provider: string,
  savedParams: Record<string, unknown> | null
): Record<string, unknown> {
  const defaultParams = initializeParameters(type, provider);

  if (!savedParams) return defaultParams;

  // Override defaults with saved values
  return { ...defaultParams, ...savedParams };
}
