import { CreateVoiceAgentRequest, UpdateVoiceAgentRequest, VoiceAgent } from '@app/types/voice-agent';
import { fromEditorText } from '../conversation-config';
import { VoiceAgentInput } from './voice-agent-form';

const E164_REGEX = /^\+[1-9]\d{1,14}$/;

/** The agent as the form describes it, validated and cleaned up: the shape both create and update start from. */
export interface VoiceAgentFields {
  name: string;
  description: string | null;
  llm_config_id: string;
  tts_config_id: string;
  stt_config_id: string;
  telephony_config_id: string;
  tts_voice_ids: Record<string, string>;
  tts_parameters: Record<string, unknown> | null;
  stt_parameters: Record<string, unknown> | null;
  system_prompt: string;
  welcome_message: string;
  conversation_config: Record<string, unknown> | null;
  status: VoiceAgent['status'];
  inbound_numbers: string[];
  outbound_numbers: string[];
  supported_languages: string[];
  default_language: string;
}

/** A provider's settings as edited, and the parameters that provider supports. */
export interface ProviderSettings {
  values: Record<string, unknown>;
  supported?: Record<string, unknown>;
}

/**
 * The settings worth sending: ones the provider supports and that have a value. `language` is left out because
 * the agent's supported languages decide it. Null when nothing is left.
 */
export const pickProviderParameters = ({ values, supported }: ProviderSettings): Record<string, unknown> | null => {
  const allowed = new Set(Object.keys(supported ?? {}).filter((key) => key !== 'language'));
  const picked = Object.fromEntries(
    Object.entries(values).filter(
      ([key, value]) => allowed.has(key) && value !== '' && value !== undefined && value !== null
    )
  );
  return Object.keys(picked).length > 0 ? picked : null;
};

/** A comma-separated list of phone numbers, without blanks. */
export const parsePhoneNumbers = (input: string | undefined): string[] =>
  (input ?? '')
    .split(',')
    .map((number) => number.trim())
    .filter(Boolean);

const invalidNumbersError = (direction: string, numbers: string[]) => {
  const invalid = numbers.filter((number) => !E164_REGEX.test(number));
  return invalid.length > 0
    ? `Invalid ${direction} phone numbers (must be E.164 format): ${invalid.join(', ')}`
    : undefined;
};

/** Checks what the schema can't (JSON, phone formats, the default language) and cleans up the values. */
export const buildVoiceAgentFields = (
  data: VoiceAgentInput,
  providers: { tts: ProviderSettings; stt: ProviderSettings }
): { ok: true; fields: VoiceAgentFields } | { ok: false; error: string } => {
  const conversationConfig = fromEditorText(data.conversation_config);
  if (conversationConfig === undefined) {
    return { ok: false, error: 'Conversation configuration must be a valid JSON object' };
  }

  const inboundNumbers = parsePhoneNumbers(data.inbound_numbers);
  const outboundNumbers = parsePhoneNumbers(data.outbound_numbers);
  const phoneError = invalidNumbersError('inbound', inboundNumbers) ?? invalidNumbersError('outbound', outboundNumbers);
  if (phoneError) return { ok: false, error: phoneError };

  if (!data.supported_languages.includes(data.default_language)) {
    return { ok: false, error: 'Default language must be one of the supported languages' };
  }

  return {
    ok: true,
    fields: {
      name: data.name.trim(),
      description: data.description?.trim() || null,
      llm_config_id: data.llm_config_id.trim(),
      tts_config_id: data.tts_config_id.trim(),
      stt_config_id: data.stt_config_id.trim(),
      telephony_config_id: data.telephony_config_id.trim(),
      tts_voice_ids: data.tts_voice_ids,
      tts_parameters: pickProviderParameters(providers.tts),
      stt_parameters: pickProviderParameters(providers.stt),
      system_prompt: data.system_prompt.trim(),
      welcome_message: (data.welcome_message || '').trim(),
      conversation_config: conversationConfig,
      status: data.status,
      inbound_numbers: inboundNumbers,
      outbound_numbers: outboundNumbers,
      supported_languages: data.supported_languages,
      default_language: data.default_language,
    },
  };
};

/** A new agent leaves out what's empty, so the server applies its defaults. */
export const toCreateRequest = (fields: VoiceAgentFields): CreateVoiceAgentRequest => ({
  ...fields,
  description: fields.description ?? undefined,
  inbound_numbers: fields.inbound_numbers.length > 0 ? fields.inbound_numbers : undefined,
  outbound_numbers: fields.outbound_numbers.length > 0 ? fields.outbound_numbers : undefined,
});

/** The saved agent in the same shape as the form's fields, filling in the defaults a blank field means. */
const savedFields = (agent: VoiceAgent): VoiceAgentFields => ({
  name: agent.name,
  description: agent.description || null,
  llm_config_id: agent.llm_config_id,
  tts_config_id: agent.tts_config_id,
  stt_config_id: agent.stt_config_id,
  telephony_config_id: agent.telephony_config_id,
  tts_voice_ids: agent.tts_voice_ids,
  tts_parameters: agent.tts_parameters || null,
  stt_parameters: agent.stt_parameters || null,
  system_prompt: agent.system_prompt,
  welcome_message: agent.welcome_message || '',
  conversation_config: agent.conversation_config || null,
  status: agent.status,
  inbound_numbers: agent.inbound_numbers || [],
  outbound_numbers: agent.outbound_numbers || [],
  supported_languages: agent.supported_languages || ['en'],
  default_language: agent.default_language,
});

/** Just the fields that differ from the saved agent, so an update never rewrites what wasn't touched. */
export const changedFields = (fields: VoiceAgentFields, agent: VoiceAgent): Partial<UpdateVoiceAgentRequest> => {
  const saved = savedFields(agent);
  const keys = Object.keys(fields) as (keyof VoiceAgentFields)[];
  return Object.fromEntries(
    keys.filter((key) => JSON.stringify(fields[key]) !== JSON.stringify(saved[key])).map((key) => [key, fields[key]])
  );
};
