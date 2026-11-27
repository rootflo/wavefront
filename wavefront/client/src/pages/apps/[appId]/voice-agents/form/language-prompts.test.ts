import { describe, expect, it } from 'vitest';
import { DEFAULT_CONVERSATION_CONFIG, DEFAULT_EDITOR_TEXT } from '../conversation-config';
import {
  keepLanguagePrompts,
  readLanguagePrompts,
  resetKeepingLanguagePrompts,
  withLanguagePrompt,
} from './language-prompts';

const EDITOR = JSON.stringify({ filler_speech: { enabled: true } }, null, 2);
const WITH_PACKS = JSON.stringify(
  { filler_speech: { enabled: true }, language_prompts: { hi: 'Hindi rules', ta: 'Tamil rules' } },
  null,
  2
);

describe('readLanguagePrompts', () => {
  it('reads the packs and nothing else', () => {
    expect(readLanguagePrompts(WITH_PACKS)).toEqual({ hi: 'Hindi rules', ta: 'Tamil rules' });
    expect(readLanguagePrompts(EDITOR)).toEqual({});
    expect(readLanguagePrompts('')).toEqual({});
  });

  it('is undefined while the JSON is being edited', () => {
    expect(readLanguagePrompts('{ "filler_speech": ')).toBeUndefined();
    expect(readLanguagePrompts('[1, 2]')).toBeUndefined();
  });
});

describe('withLanguagePrompt', () => {
  it('adds a pack and keeps every other setting', () => {
    const next = JSON.parse(withLanguagePrompt(EDITOR, 'ta', 'Tamil rules')!);
    expect(next).toEqual({ filler_speech: { enabled: true }, language_prompts: { ta: 'Tamil rules' } });
  });

  it('removes a pack when emptied, and the key when none are left', () => {
    const one = JSON.parse(withLanguagePrompt(WITH_PACKS, 'hi', '  ')!);
    expect(one.language_prompts).toEqual({ ta: 'Tamil rules' });
    const none = JSON.parse(withLanguagePrompt(JSON.stringify(one), 'ta', '')!);
    expect(none).toEqual({ filler_speech: { enabled: true } });
  });

  it('does nothing while the JSON is invalid', () => {
    expect(withLanguagePrompt('{ broken', 'ta', 'x')).toBeUndefined();
  });
});

describe('keepLanguagePrompts', () => {
  it("drops an unchecked language's pack", () => {
    const next = JSON.parse(keepLanguagePrompts(WITH_PACKS, ['en', 'ta'])!);
    expect(next.language_prompts).toEqual({ ta: 'Tamil rules' });
  });

  it('returns the text untouched when nothing is dropped or the JSON is invalid', () => {
    expect(keepLanguagePrompts(WITH_PACKS, ['en', 'hi', 'ta'])).toBe(WITH_PACKS);
    expect(keepLanguagePrompts('{ broken', ['en'])).toBe('{ broken');
  });
});

describe('resetKeepingLanguagePrompts', () => {
  it('resets every option to its default and keeps the packs', () => {
    expect(JSON.parse(resetKeepingLanguagePrompts(WITH_PACKS))).toEqual({
      ...DEFAULT_CONVERSATION_CONFIG,
      language_prompts: { hi: 'Hindi rules', ta: 'Tamil rules' },
    });
  });

  it('gives the plain defaults when there are no packs or the JSON is invalid', () => {
    expect(resetKeepingLanguagePrompts(EDITOR)).toBe(DEFAULT_EDITOR_TEXT);
    expect(resetKeepingLanguagePrompts('')).toBe(DEFAULT_EDITOR_TEXT);
    expect(resetKeepingLanguagePrompts('{ broken')).toBe(DEFAULT_EDITOR_TEXT);
  });
});
