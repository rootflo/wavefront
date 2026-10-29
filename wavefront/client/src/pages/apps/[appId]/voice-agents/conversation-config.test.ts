import { describe, expect, it } from 'vitest';
import {
  BUILT_IN_CHOICE_WORDS,
  CONVERSATION_CONFIG_DOCS,
  DEFAULT_CONVERSATION_CONFIG,
  isOutOfRange,
  splitSectionOptions,
} from './conversation-config';

const turnTaking = CONVERSATION_CONFIG_DOCS.find((doc) => doc.section === 'turn_taking')!;
const keys = (options: { key: string }[]) => options.map((option) => option.key);
const option = (key: string) => turnTaking.options.find((o) => o.key === key)!;

describe('isOutOfRange', () => {
  const idleTimeout = option('idle_timeout_ms');

  it('accepts 0 (off) and values inside the on range', () => {
    for (const value of [0, 2000, 5000, 60000]) expect(isOutOfRange(idleTimeout, value)).toBe(false);
  });

  it('flags a non-zero timeout the service would raise to its minimum', () => {
    for (const value of [1, 500, 1999]) expect(isOutOfRange(idleTimeout, value)).toBe(true);
  });

  it('flags values beyond min and max', () => {
    expect(isOutOfRange(idleTimeout, 60001)).toBe(true);
    expect(isOutOfRange(idleTimeout, -1)).toBe(true);
    expect(isOutOfRange(option('vad_stop_ms'), 50)).toBe(true);
  });

  it('ignores unset values and non-number options', () => {
    expect(isOutOfRange(idleTimeout, undefined)).toBe(false);
    expect(isOutOfRange(option('barge_in'), 5)).toBe(false);
  });
});

describe('silent-caller options', () => {
  it('all depend on the silence timeout, except the timeout itself', () => {
    const gated = turnTaking.options.filter((o) => o.requiresPositive === 'idle_timeout_ms');

    expect(keys(gated)).toEqual(['idle_max_check_ins', 'idle_fixed_goodbye', 'idle_goodbye_message']);
  });
});

describe('splitSectionOptions', () => {
  it('shows plain toggles up front and hides the rest under settings', () => {
    const { toggles, settings } = splitSectionOptions(turnTaking.options);

    expect(keys(toggles)).toEqual(['barge_in', 'mute_until_first_bot_complete']);
    expect(keys(settings)).not.toContain('barge_in');
  });

  it('keeps the missed-speech safety net with the hidden settings, on by default', () => {
    const { toggles, settings } = splitSectionOptions(turnTaking.options);

    expect(keys(toggles)).not.toContain('transcript_turn_start');
    expect(keys(settings)).toContain('transcript_turn_start');
    expect(DEFAULT_CONVERSATION_CONFIG.turn_taking.transcript_turn_start).toBe(true);
  });

  it('keeps the fixed-goodbye toggle with the hidden settings, right before its message', () => {
    const settingKeys = keys(splitSectionOptions(turnTaking.options).settings);
    const toggleAt = settingKeys.indexOf('idle_fixed_goodbye');

    expect(toggleAt).toBeGreaterThan(-1);
    expect(settingKeys[toggleAt + 1]).toBe('idle_goodbye_message');
  });
});

describe('language switching', () => {
  const languageSwitch = CONVERSATION_CONFIG_DOCS.find((doc) => doc.section === 'language_switch')!;

  it('offers the direct switch as a visible tickbox, off by default', () => {
    const { toggles } = splitSectionOptions(languageSwitch.options);

    expect(keys(toggles)).toEqual(['direct_switch']);
    expect(DEFAULT_CONVERSATION_CONFIG.language_switch.direct_switch).toBe(false);
  });

  it('documents every default it writes out', () => {
    const documented = keys(languageSwitch.options);

    for (const key of Object.keys(DEFAULT_CONVERSATION_CONFIG.language_switch)) expect(documented).toContain(key);
  });

  it('offers per-language choice words, only once the direct switch is on, starting from the built-ins', () => {
    const choiceWords = languageSwitch.options.find((o) => o.key === 'choice_words')!;

    expect(choiceWords.kind).toBe('phrases');
    expect(choiceWords.requires).toBe('direct_switch');
    expect(choiceWords.builtInPhrases).toBe(BUILT_IN_CHOICE_WORDS);
    expect(keys(splitSectionOptions(languageSwitch.options).settings)).toEqual(['choice_words']);
  });

  it('keeps built-in choice words to single lower-case words', () => {
    for (const words of Object.values(BUILT_IN_CHOICE_WORDS)) {
      for (const word of words) expect(word).toBe(word.toLowerCase().trim());
      for (const word of words) expect(word.split(/\s+/)).toHaveLength(1);
    }
  });
});
