/**
 * Language packs: `conversation_config.language_prompts` ({"ta": "...", ...}).
 *
 * A pack holds rules and examples for one language only. On a call it is added
 * after the main prompt while the call is in that language, and swapped on a
 * language switch (call_processing's prompt_layout.py), so the main prompt stays
 * cached. The form keeps `conversation_config` as the Advanced tab's JSON text;
 * these helpers read and write packs inside that same text, so there is one
 * source of truth.
 */

import { DEFAULT_CONVERSATION_CONFIG } from '../conversation-config';

export const MAX_LANGUAGE_PROMPT_CHARS = 20_000;

type ConfigObject = Record<string, unknown>;

const isObject = (value: unknown): value is ConfigObject =>
  !!value && typeof value === 'object' && !Array.isArray(value);

/** The editor text as an object; `{}` when empty, `undefined` when not valid JSON. */
const parseConfig = (text: string | undefined): ConfigObject | undefined => {
  const trimmed = (text ?? '').trim();
  if (!trimmed) return {};
  try {
    const parsed: unknown = JSON.parse(trimmed);
    return isObject(parsed) ? parsed : undefined;
  } catch {
    return undefined;
  }
};

const withPacks = (config: ConfigObject, packs: Record<string, string>): string => {
  const next = { ...config };
  if (Object.keys(packs).length > 0) next.language_prompts = packs;
  else delete next.language_prompts;
  return JSON.stringify(next, null, 2);
};

/** The packs in the editor text, or `undefined` while the text is not valid JSON. */
export const readLanguagePrompts = (text: string | undefined): Record<string, string> | undefined => {
  const config = parseConfig(text);
  if (!config) return undefined;
  const packs = config.language_prompts;
  if (!isObject(packs)) return {};
  return Object.fromEntries(
    Object.entries(packs).filter((entry): entry is [string, string] => typeof entry[1] === 'string')
  );
};

/** New editor text with one language's pack set (an empty pack removes it). */
export const withLanguagePrompt = (text: string | undefined, language: string, prompt: string): string | undefined => {
  const config = parseConfig(text);
  const packs = readLanguagePrompts(text);
  if (!config || !packs) return undefined;
  const next = { ...packs };
  if (prompt.trim()) next[language] = prompt;
  else delete next[language];
  return withPacks(config, next);
};

/** "Reset to defaults" on the Advanced tab: every option back to its default, packs kept (that tab hides them). */
export const resetKeepingLanguagePrompts = (text: string | undefined): string =>
  withPacks(DEFAULT_CONVERSATION_CONFIG, readLanguagePrompts(text) ?? {});

/** New editor text without the packs of languages no longer supported (unchanged if none). */
export const keepLanguagePrompts = (text: string | undefined, languages: string[]): string | undefined => {
  const config = parseConfig(text);
  const packs = readLanguagePrompts(text);
  if (!config || !packs) return text;
  const kept = Object.fromEntries(Object.entries(packs).filter(([language]) => languages.includes(language)));
  if (Object.keys(kept).length === Object.keys(packs).length) return text;
  return withPacks(config, kept);
};
