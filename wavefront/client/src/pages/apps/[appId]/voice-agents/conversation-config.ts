/**
 * Conversation configuration for voice agents (`voice_agent.conversation_config`).
 *
 * The defaults here mirror the call-processing service (`turn_taking.py`,
 * `filler_speech.py`): a bot with no config behaves exactly like this JSON, so the
 * editor can show it as the starting point.
 */

export type ConversationConfig = Record<string, unknown>;

export const DEFAULT_CONVERSATION_CONFIG = {
  turn_taking: {
    barge_in: true,
    barge_in_min_words: 0,
    mute_until_first_bot_complete: false,
    vad_confidence: 0.75,
    vad_min_volume: 0.65,
    vad_start_ms: 200,
    vad_stop_ms: 200,
    end_of_turn_timeout_ms: 3000,
  },
  filler_speech: {
    thinking: true,
    thinking_delay_ms: 800,
    before_tool_call: false,
  },
  end_conversation: {
    enabled: false,
    farewell_message: 'Thank you for using our service! Goodbye!',
  },
} as const satisfies ConversationConfig;

export interface ConfigOptionDoc {
  key: string;
  defaultValue: string;
  range: string;
  description: string;
}

export interface ConfigSectionDoc {
  section: keyof typeof DEFAULT_CONVERSATION_CONFIG;
  title: string;
  summary: string;
  options: ConfigOptionDoc[];
}

export const CONVERSATION_CONFIG_DOCS: ConfigSectionDoc[] = [
  {
    section: 'turn_taking',
    title: 'Turn taking',
    summary: 'When the bot decides the user has started or finished speaking, and when the user can interrupt it.',
    options: [
      {
        key: 'barge_in',
        defaultValue: 'true',
        range: 'true / false',
        description:
          'Let the user interrupt the bot while it is talking. Set to false and the bot always finishes what it is saying (including the welcome message): anything the user says over it is ignored, and if they are still speaking when the bot finishes, they are heard from that point.',
      },
      {
        key: 'barge_in_min_words',
        defaultValue: '0',
        range: '0 – 10',
        description:
          'Only used when barge_in is true. Words the user must say to interrupt the bot. 0 interrupts the moment any speech is heard (fastest, but noise or echo can cut the bot off). 1 waits for a transcribed word; raise it on noisy lines so coughs and background talk do not cut the bot off.',
      },
      {
        key: 'mute_until_first_bot_complete',
        defaultValue: 'false',
        range: 'true / false',
        description:
          'Play the welcome message to the end before the bot listens: nothing the user says during it is heard, whatever the barge-in setting. After the welcome, barge-in applies as usual. Needs a welcome message (ignored without one), and only applies to the first agent of a call, not one switched to mid-call.',
      },
      {
        key: 'vad_confidence',
        defaultValue: '0.75',
        range: '0.3 – 0.95',
        description:
          'How sure the voice detector must be that a sound is speech. Lower catches quiet speakers; higher ignores more background noise.',
      },
      {
        key: 'vad_min_volume',
        defaultValue: '0.65',
        range: '0 – 0.95',
        description: 'Audio quieter than this is ignored. Lower for soft-spoken users, higher for noisy environments.',
      },
      {
        key: 'vad_start_ms',
        defaultValue: '200',
        range: '50 – 1000',
        description:
          'How long the user must speak before their turn starts. Lower reacts faster but picks up short noises.',
      },
      {
        key: 'vad_stop_ms',
        defaultValue: '200',
        range: '100 – 2000',
        description:
          'Silence before the bot checks whether the user is done. Every reply waits at least this long. Raise it only if the bot keeps answering before the user finishes.',
      },
      {
        key: 'end_of_turn_timeout_ms',
        defaultValue: '3000',
        range: '500 – 10000',
        description:
          'When the user pauses mid-sentence, how much silence makes the bot reply anyway. Lower feels snappier but can talk over users who pause to think.',
      },
    ],
  },
  {
    section: 'filler_speech',
    title: 'Filler speech',
    summary: 'Short phrases the bot says while it works, so the call is never silent.',
    options: [
      {
        key: 'thinking',
        defaultValue: 'true',
        range: 'true / false',
        description:
          'Say a short backchannel ("Hmm", "Okay") if the AI is slow to start replying. Fast replies get no filler.',
      },
      {
        key: 'thinking_delay_ms',
        defaultValue: '800',
        range: '0 – 5000',
        description: 'How long to wait for the reply before saying the thinking filler. Lower plays it more often.',
      },
      {
        key: 'thinking_phrases',
        defaultValue: 'built-in',
        range: '{ "en": ["Hmm"] }',
        description:
          'Optional. Your own thinking phrases per language code. Languages you leave out keep the built-in phrases (en, hi, ta, te, ml, kn).',
      },
      {
        key: 'before_tool_call',
        defaultValue: 'false',
        range: 'true / false',
        description: 'Say a short phrase ("One moment please") before running a tool that may take a while.',
      },
      {
        key: 'tool_call_phrases',
        defaultValue: 'built-in',
        range: '{ "en": ["One sec"] }',
        description:
          'Optional. Your own tool-wait phrases per language code. Languages you leave out keep the built-ins.',
      },
    ],
  },
  {
    section: 'end_conversation',
    title: 'Ending the call',
    summary:
      'Lets the bot hang up by itself after a clear goodbye. Off by default: the bot never ends the call on its own and keeps listening until the user hangs up.',
    options: [
      {
        key: 'enabled',
        defaultValue: 'false',
        range: 'true / false',
        description:
          'Turn on to let the AI end the call after the user says goodbye or that they are done. A "thank you" in the middle of the conversation does not end it.',
      },
      {
        key: 'farewell_message',
        defaultValue: 'Thank you for using our service! Goodbye!',
        range: 'text',
        description:
          'What the bot says before hanging up, unless the AI chooses its own goodbye. Only used when enabled.',
      },
    ],
  },
];

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

export const isDeepEqual = (a: unknown, b: unknown): boolean => {
  if (a === b) return true;
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((item, i) => isDeepEqual(item, b[i]));
  }
  if (isPlainObject(a) && isPlainObject(b)) {
    const keys = Object.keys(a);
    return keys.length === Object.keys(b).length && keys.every((key) => key in b && isDeepEqual(a[key], b[key]));
  }
  return false;
};

/** Adds every default the config does not set yet; values the user set are kept. */
export const withDefaults = (
  config: ConversationConfig,
  defaults: ConversationConfig = DEFAULT_CONVERSATION_CONFIG
) => {
  const merged: ConversationConfig = { ...config };
  Object.entries(defaults).forEach(([key, defaultValue]) => {
    const current = merged[key];
    if (current === undefined) {
      merged[key] = defaultValue;
    } else if (isPlainObject(current) && isPlainObject(defaultValue)) {
      merged[key] = withDefaults(current, defaultValue);
    }
  });
  return merged;
};

const pretty = (config: ConversationConfig) => JSON.stringify(config, null, 2);

/** Editor text for a stored config: bots with none show the defaults. */
export const toEditorText = (stored: ConversationConfig | null | undefined): string =>
  pretty(stored && Object.keys(stored).length > 0 ? stored : DEFAULT_CONVERSATION_CONFIG);

export const DEFAULT_EDITOR_TEXT = pretty(DEFAULT_CONVERSATION_CONFIG);

/**
 * What to store for the editor text. Unchanged defaults (or `{}`) store `null`, so
 * those bots keep following the service defaults rather than a frozen copy.
 * Returns `undefined` when the text is not valid JSON object.
 */
export const fromEditorText = (text: string | undefined): ConversationConfig | null | undefined => {
  const trimmed = (text ?? '').trim();
  if (!trimmed || trimmed === '{}') return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    return undefined;
  }
  if (!isPlainObject(parsed)) return undefined;
  if (Object.keys(parsed).length === 0 || isDeepEqual(parsed, DEFAULT_CONVERSATION_CONFIG)) return null;
  return parsed;
};
