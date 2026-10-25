import { VoiceAgent } from '@app/types/voice-agent';
import { describe, expect, it } from 'vitest';
import { toFormValues } from './voice-agent-form';
import {
  buildVoiceAgentFields,
  changedFields,
  parsePhoneNumbers,
  pickProviderParameters,
  toCreateRequest,
} from './voice-agent-request';

const agent: VoiceAgent = {
  id: 'agent-1',
  name: 'Support line',
  description: null,
  status: 'active',
  supported_languages: ['en'],
  default_language: 'en',
  is_deleted: false,
  created_at: '',
  updated_at: '',
  llm_config_id: 'llm-1',
  tts_config_id: 'tts-1',
  stt_config_id: 'stt-1',
  telephony_config_id: 'tel-1',
  system_prompt: 'You are helpful.',
  welcome_message: '',
  tts_voice_ids: { en: 'voice-1' },
  tts_parameters: { sample_rate: 16000 },
  stt_parameters: null,
  conversation_config: null,
  inbound_numbers: ['+14155550100'],
  outbound_numbers: [],
};

const providers = {
  tts: { values: { sample_rate: 16000 }, supported: { sample_rate: {}, language: {} } },
  stt: { values: {}, supported: {} },
};

const build = (overrides: Partial<ReturnType<typeof toFormValues>> = {}) =>
  buildVoiceAgentFields({ ...toFormValues(agent), ...overrides }, providers);

describe('pickProviderParameters', () => {
  it('keeps supported settings with a value, and never language', () => {
    expect(
      pickProviderParameters({
        values: { speed: 1.2, pitch: '', language: 'en', old_setting: 3 },
        supported: { speed: {}, pitch: {}, language: {} },
      })
    ).toEqual({ speed: 1.2 });
  });

  it('is null when nothing is left to send', () => {
    expect(pickProviderParameters({ values: { pitch: undefined }, supported: { pitch: {} } })).toBeNull();
  });
});

describe('parsePhoneNumbers', () => {
  it('splits on commas and drops blanks', () => {
    expect(parsePhoneNumbers(' +14155550100, ,+442071838750 ')).toEqual(['+14155550100', '+442071838750']);
    expect(parsePhoneNumbers(undefined)).toEqual([]);
  });
});

describe('buildVoiceAgentFields', () => {
  it('rejects conversation config that is not a JSON object', () => {
    expect(build({ conversation_config: '[1, 2]' })).toEqual({
      ok: false,
      error: 'Conversation configuration must be a valid JSON object',
    });
  });

  it('names the phone numbers that are not E.164, inbound first', () => {
    expect(build({ inbound_numbers: '+14155550100, 555-0100', outbound_numbers: 'nope' })).toEqual({
      ok: false,
      error: 'Invalid inbound phone numbers (must be E.164 format): 555-0100',
    });
  });

  it('needs the default language to be a supported one', () => {
    expect(build({ supported_languages: ['en'], default_language: 'fr' })).toMatchObject({ ok: false });
  });

  it('trims text and turns a blank description into null', () => {
    const result = build({ name: '  Support line  ', description: '   ' });
    expect(result.ok && result.fields).toMatchObject({ name: 'Support line', description: null });
  });
});

describe('changedFields', () => {
  it('is empty for an untouched agent', () => {
    const result = build();
    expect(result.ok && changedFields(result.fields, agent)).toEqual({});
  });

  it('lists only what changed, comparing lists and settings by value', () => {
    const result = buildVoiceAgentFields(
      { ...toFormValues(agent), name: 'Billing line', inbound_numbers: '+14155550100, +14155550101' },
      { ...providers, tts: { ...providers.tts, values: {} } }
    );
    expect(result.ok && changedFields(result.fields, agent)).toEqual({
      name: 'Billing line',
      inbound_numbers: ['+14155550100', '+14155550101'],
      tts_parameters: null,
    });
  });
});

describe('toCreateRequest', () => {
  it('leaves out an empty description and empty number lists', () => {
    const result = build({ inbound_numbers: '' });
    const request = result.ok ? toCreateRequest(result.fields) : null;
    expect(request).toMatchObject({ name: 'Support line', description: undefined, inbound_numbers: undefined });
  });
});
