import { DEFAULT_EDITOR_TEXT, toEditorText } from '../conversation-config';
import { VoiceAgent } from '@app/types/voice-agent';
import { z } from 'zod';

// The voice agent form: its tabs, schema, and conversion from a saved agent

export const FORM_TAB = {
  BASIC: 'basic',
  CONFIGURATIONS: 'configurations',
  LANGUAGES: 'languages',
  BEHAVIOR: 'behavior',
  TOOLS: 'tools',
  ADVANCED: 'advanced',
  GUIDE: 'guide',
} as const;

export type FormTab = (typeof FORM_TAB)[keyof typeof FORM_TAB];

export const isFormTab = (value: string): value is FormTab => Object.values(FORM_TAB).includes(value as FormTab);

// Voice IDs are required for a new agent; an existing one can be saved without touching them
export const buildSchema = (isEdit: boolean) =>
  z.object({
    name: z.string().min(1, 'Name is required').max(100, 'Name must be 100 characters or less'),
    description: z.string().max(500, 'Description must be 500 characters or less').optional(),
    llm_config_id: z.string().min(1, 'Model is required'),
    tts_config_id: z.string().min(1, 'TTS configuration is required'),
    stt_config_id: z.string().min(1, 'STT configuration is required'),
    telephony_config_id: z.string().min(1, 'Telephony configuration is required'),
    tts_voice_ids: isEdit
      ? z.record(z.string(), z.string())
      : z
          .record(z.string(), z.string().min(1, 'Voice ID must not be empty'))
          .refine((val) => Object.keys(val).length > 0, {
            message: 'At least one voice ID is required',
          }),
    system_prompt: z.string().min(1, 'System prompt is required'),
    welcome_message: z.string(),
    conversation_config: z.string().optional(),
    status: z.enum(['active', 'inactive']),
    inbound_numbers: z.string().optional(),
    outbound_numbers: z.string().optional(),
    supported_languages: z.array(z.string()).min(1, 'At least one language is required'),
    default_language: z.string().min(1, 'Default language is required'),
  });

export type VoiceAgentInput = z.infer<ReturnType<typeof buildSchema>>;

export const FIELD_TAB_MAP: Record<keyof VoiceAgentInput, FormTab> = {
  name: FORM_TAB.BASIC,
  description: FORM_TAB.BASIC,
  status: FORM_TAB.BASIC,
  llm_config_id: FORM_TAB.CONFIGURATIONS,
  tts_config_id: FORM_TAB.CONFIGURATIONS,
  stt_config_id: FORM_TAB.CONFIGURATIONS,
  telephony_config_id: FORM_TAB.CONFIGURATIONS,
  tts_voice_ids: FORM_TAB.CONFIGURATIONS,
  inbound_numbers: FORM_TAB.BASIC,
  outbound_numbers: FORM_TAB.BASIC,
  supported_languages: FORM_TAB.LANGUAGES,
  default_language: FORM_TAB.LANGUAGES,
  system_prompt: FORM_TAB.BEHAVIOR,
  welcome_message: FORM_TAB.BEHAVIOR,
  conversation_config: FORM_TAB.ADVANCED,
};

export const toFormValues = (agent?: VoiceAgent): VoiceAgentInput => ({
  name: agent?.name ?? '',
  description: agent?.description || '',
  llm_config_id: agent?.llm_config_id ?? '',
  tts_config_id: agent?.tts_config_id ?? '',
  stt_config_id: agent?.stt_config_id ?? '',
  telephony_config_id: agent?.telephony_config_id ?? '',
  tts_voice_ids: agent?.tts_voice_ids ?? { en: '' },
  system_prompt: agent?.system_prompt ?? '',
  welcome_message: agent?.welcome_message ?? '',
  conversation_config: agent ? toEditorText(agent.conversation_config) : DEFAULT_EDITOR_TEXT,
  status: agent?.status ?? 'inactive',
  inbound_numbers: agent?.inbound_numbers?.join(', ') || '',
  outbound_numbers: agent?.outbound_numbers?.join(', ') || '',
  supported_languages: agent?.supported_languages || ['en'],
  default_language: agent?.default_language || 'en',
});

/** Per-language voices count as customized once they stop being one shared voice. */
export const hasCustomVoices = (agent?: VoiceAgent) => {
  const ids = Object.values(agent?.tts_voice_ids || {});
  return ids.length > 1 && new Set(ids).size > 1;
};

export type ParameterKind = 'tts' | 'stt';
