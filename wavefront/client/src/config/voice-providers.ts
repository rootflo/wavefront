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
    providers: ['elevenlabs', 'deepgram', 'cartesia', 'sarvam', 'azure'] as const,
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
            default: 'eleven_flash_v2_5',
            description: 'ElevenLabs TTS model',
            options: [
              'eleven_v4_turbo',
              'eleven_v4',
              'eleven_v3_conversational',
              'eleven_v3',
              'eleven_flash_v2_5',
              'eleven_flash_v2',
              'eleven_multilingual_v2',
              'eleven_turbo_v2_5',
              'eleven_turbo_v2',
            ],
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
            step: 0.01,
            description: 'Controls voice consistency (0-1)',
          },
          similarity_boost: {
            type: 'number',
            default: 0.75,
            min: 0,
            max: 1,
            step: 0.01,
            description: 'Enhances voice similarity (0-1)',
          },
          style: {
            type: 'number',
            default: 0.0,
            min: 0,
            max: 1,
            step: 0.01,
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
            step: 0.01,
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
            options: ['linear16', 'mulaw', 'alaw', 'mp3', 'opus', 'flac', 'aac'],
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
            default: 'sonic-3.6',
            description: 'Cartesia TTS model',
            options: ['sonic-3.6', 'sonic-3.5', 'sonic-3', 'sonic-preview', 'sonic-2', 'sonic-turbo'],
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
            step: 0.01,
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
            default: 'bulbul:v4-flash',
            options: ['bulbul:v4-flash', 'bulbul:v3', 'bulbul:v2'],
            description: 'TTS model',
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
            step: 0.01,
            description: 'Voice pitch (-0.75 to 0.75)',
          },
          pace: {
            type: 'number',
            default: 1.0,
            min: 0.3,
            max: 3.0,
            step: 0.01,
            description: 'Speech pace (0.3-3.0)',
          },
          loudness: {
            type: 'number',
            default: 1.0,
            min: 0.1,
            max: 3.0,
            step: 0.01,
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
            step: 0.01,
            description: 'Randomness for bulbul v3 (0.01-1.0)',
          },
        },
      },
      azure: {
        name: 'Azure',
        badge: {
          bg: 'bg-sky-100',
          text: 'text-sky-700',
        },
        parameters: {
          style: {
            type: 'string' as const,
            default: '',
            description: 'Speaking style',
            options: [
              'cheerful',
              'sad',
              'angry',
              'excited',
              'friendly',
              'hopeful',
              'shouting',
              'terrified',
              'unfriendly',
              'whispering',
              'newscast',
              'customerservice',
              'assistant',
              'chat',
              'empathetic',
              'narration-professional',
            ],
          },
          rate: {
            type: 'string' as const,
            default: '',
            description: 'Speech rate',
            options: ['x-slow', 'slow', 'medium', 'fast', 'x-fast', '-20%', '-10%', '+0%', '+10%', '+20%'],
          },
          pitch: {
            type: 'string' as const,
            default: '',
            description: 'Pitch adjustment',
            options: ['x-low', 'low', 'medium', 'high', 'x-high', '-50Hz', '+0Hz', '+50Hz'],
          },
          role: {
            type: 'string' as const,
            default: '',
            description: 'Voice role for expression',
            options: [
              'Girl',
              'Boy',
              'YoungAdultFemale',
              'YoungAdultMale',
              'OlderAdultFemale',
              'OlderAdultMale',
              'SeniorFemale',
              'SeniorMale',
            ],
          },
          style_degree: {
            type: 'string' as const,
            default: '',
            description: 'Intensity of speaking style (0.01 to 2.0)',
            options: ['0.5', '1.0', '1.5', '2.0'],
          },
          volume: {
            type: 'string' as const,
            default: '',
            description: 'Volume level',
            options: ['silent', 'x-soft', 'soft', 'medium', 'loud', 'x-loud', '-20%', '+0%', '+20%'],
          },
          sample_rate: {
            type: 'number' as const,
            default: undefined,
            description: 'Audio sample rate in Hz',
            placeholder: '16000',
          },
        },
      },
    },
  },
  stt: {
    providers: ['deepgram', 'sarvam', 'elevenlabs', 'azure'] as const,
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
            default: 'nova-3-general',
            description: 'Deepgram STT model / profile',
            options: [
              'nova-3',
              'nova-3-general',
              'nova-3-medical',
              'nova-3-pharma',
              'nova-2',
              'nova-2-general',
              'nova-2-phonecall',
              'nova-2-meeting',
              'nova-2-voicemail',
              'nova-2-finance',
              'nova-2-conversationalai',
              'nova-2-video',
              'nova-2-medical',
              'nova-2-drivethru',
              'nova-2-automotive',
              'nova-2-atc',
            ],
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
            options: ['linear16', 'mulaw', 'alaw', 'mp3', 'opus', 'flac', 'aac'],
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
            default: 'saaras:v3',
            options: ['saaras:v3', 'saaras:v4'],
            description: 'STT model (saaras:v4 needs Pipecat ≥1.12)',
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
            options: ['scribe_v2_realtime', 'scribe_v2', 'scribe_v2_medical'],
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
      azure: {
        name: 'Azure',
        badge: {
          bg: 'bg-sky-100',
          text: 'text-sky-700',
        },
        parameters: {
          endpoint_id: {
            type: 'string' as const,
            default: '',
            description: 'Custom model endpoint ID (optional)',
            placeholder: '',
          },
          sample_rate: {
            type: 'number' as const,
            default: undefined,
            description: 'Audio sample rate in Hz',
            placeholder: '8000',
          },
          ttfs_p99_latency: {
            type: 'number' as const,
            default: undefined,
            description: 'P99 latency threshold in seconds for first speech detection',
            placeholder: '1.5',
            step: 0.1,
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

export interface ParamKeyGroups {
  compact: string[];
  sliders: string[];
  booleans: string[];
}

/**
 * Parameter keys grouped for 2-col layout: compact fields, then sliders,
 * then checkboxes (enable_preprocessing first). Each group starts a new row.
 */
export function groupParamKeys(parameters: Record<string, ParameterConfig>): ParamKeyGroups {
  const keys = Object.keys(parameters).filter((key) => key !== 'language');
  const isSlider = (key: string) => {
    const param = parameters[key];
    return param.type === 'number' && param.min !== undefined && param.max !== undefined;
  };
  const isBoolean = (key: string) => parameters[key].type === 'boolean';

  const compact = keys.filter((key) => !isSlider(key) && !isBoolean(key));
  const sliders = keys.filter(isSlider);
  const booleans = keys.filter(isBoolean);

  return {
    compact: compact.includes('model') ? ['model', ...compact.filter((key) => key !== 'model')] : compact,
    sliders,
    booleans: booleans.includes('enable_preprocessing')
      ? ['enable_preprocessing', ...booleans.filter((key) => key !== 'enable_preprocessing')]
      : booleans,
  };
}

/** Flat order: compact → sliders → booleans (enable_preprocessing first among booleans). */
export function orderedParamKeys(parameters: Record<string, ParameterConfig>): string[] {
  const { compact, sliders, booleans } = groupParamKeys(parameters);
  return [...compact, ...sliders, ...booleans];
}
