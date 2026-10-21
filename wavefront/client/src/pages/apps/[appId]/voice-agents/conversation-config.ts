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
    thinking: false,
    thinking_delay_ms: 800,
    before_tool_call: false,
  },
  end_conversation: {
    enabled: false,
    farewell_message: 'Thank you for using our service! Goodbye!',
  },
} as const satisfies ConversationConfig;

/** Built-in phrases from the call-processing service (`constants/filler_phrases.py`). */
export const BUILT_IN_THINKING_PHRASES: Record<string, string[]> = {
  en: ['Hmm', 'Okay', 'Right', 'Let me see'],
  hi: ['हम्म', 'अच्छा', 'ठीक है', 'देखती हूँ'],
  ta: ['ம்ம்', 'சரி', 'பார்க்கிறேன்'],
  te: ['హ్మ్', 'సరే', 'చూస్తాను'],
  ml: ['ഹ്മ്', 'ശരി', 'നോക്കട്ടെ'],
  kn: ['ಹ್ಮ್', 'ಸರಿ', 'ನೋಡುತ್ತೇನೆ'],
};

export const BUILT_IN_TOOL_CALL_PHRASES: Record<string, string[]> = {
  en: ['Please wait a moment', 'Just a second', 'Give me a moment', 'One moment please'],
  hi: ['कृपया एक पल प्रतीक्षा करें', 'बस एक सेकंड', 'मुझे एक पल दें', 'एक पल रुकिए'],
  ta: ['தயவுசெய்து ஒரு நிமிடம் காத்திருக்கவும்', 'ஒரு நொடி', 'எனக்கு ஒரு நிமிடம் கொடுங்கள்', 'ஒரு நிமிடம்'],
  te: ['దయచేసి ఒక్క క్షణం వేచి ఉండండి', 'ఒక్క నిమిషం', 'నాకు ఒక్క క్షణం ఇవ్వండి', 'ఒక్క క్షణం దయచేసి'],
  ml: ['ദയവായി ഒരു നിമിഷം കാത്തിരിക്കൂ', 'ഒരു സെക്കൻഡ്', 'എനിക്ക് ഒരു നിമിഷം തരൂ', 'ഒരു നിമിഷം ദയവായി'],
  kn: ['ದಯವಿಟ್ಟು ಒಂದು ಕ್ಷಣ ಕಾಯಿರಿ', 'ಒಂದು ಕ್ಷಣ', 'ನನಗೆ ಒಂದು ಕ್ಷಣ ನೀಡಿ', 'ಒಂದು ಕ್ಷಣ ದಯವಿಟ್ಟು'],
};

export interface ConfigOptionDoc {
  key: string;
  label: string;
  /** Which input edits it: phrases are per-language lists (`{ "en": ["Hmm"] }`). */
  kind: 'boolean' | 'number' | 'text' | 'phrases';
  min?: number;
  max?: number;
  step?: number;
  /** Boolean option in the same section that must be on for this one to matter. */
  requires?: string;
  /** For phrases: what the service says for languages the bot does not customise. */
  builtInPhrases?: Record<string, string[]>;
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
        label: 'Let the user interrupt (barge-in)',
        kind: 'boolean',
        defaultValue: 'true',
        range: 'true / false',
        description:
          'Let the user interrupt the bot while it is talking. Set to false and the bot always finishes what it is saying (including the welcome message): anything the user says over it is ignored, and if they are still speaking when the bot finishes, they are heard from that point.',
      },
      {
        key: 'barge_in_min_words',
        label: 'Words needed to interrupt',
        kind: 'number',
        min: 0,
        max: 10,
        step: 1,
        requires: 'barge_in',
        defaultValue: '0',
        range: '0 – 10',
        description:
          'Only used when barge_in is true. Words the user must say to interrupt the bot. 0 interrupts the moment any speech is heard (fastest, but noise or echo can cut the bot off). 1 waits for a transcribed word; raise it on noisy lines so coughs and background talk do not cut the bot off.',
      },
      {
        key: 'mute_until_first_bot_complete',
        label: 'Play the welcome message fully',
        kind: 'boolean',
        defaultValue: 'false',
        range: 'true / false',
        description:
          'Play the welcome message to the end before the bot listens: nothing the user says during it is heard, whatever the barge-in setting. After the welcome, barge-in applies as usual. Needs a welcome message (ignored without one), and only applies to the first agent of a call, not one switched to mid-call.',
      },
      {
        key: 'vad_confidence',
        label: 'Speech confidence',
        kind: 'number',
        min: 0.3,
        max: 0.95,
        step: 0.05,
        defaultValue: '0.75',
        range: '0.3 – 0.95',
        description:
          'How sure the voice detector must be that a sound is speech. Lower catches quiet speakers; higher ignores more background noise.',
      },
      {
        key: 'vad_min_volume',
        label: 'Minimum volume',
        kind: 'number',
        min: 0,
        max: 0.95,
        step: 0.05,
        defaultValue: '0.65',
        range: '0 – 0.95',
        description: 'Audio quieter than this is ignored. Lower for soft-spoken users, higher for noisy environments.',
      },
      {
        key: 'vad_start_ms',
        label: 'Speech start (ms)',
        kind: 'number',
        min: 50,
        max: 1000,
        step: 10,
        defaultValue: '200',
        range: '50 – 1000',
        description:
          'How long the user must speak before their turn starts. Lower reacts faster but picks up short noises.',
      },
      {
        key: 'vad_stop_ms',
        label: 'Speech stop (ms)',
        kind: 'number',
        min: 100,
        max: 2000,
        step: 10,
        defaultValue: '200',
        range: '100 – 2000',
        description:
          'Silence before the bot checks whether the user is done. Every reply waits at least this long. Raise it only if the bot keeps answering before the user finishes.',
      },
      {
        key: 'end_of_turn_timeout_ms',
        label: 'End-of-turn timeout (ms)',
        kind: 'number',
        min: 500,
        max: 10000,
        step: 100,
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
        label: 'Say a filler while thinking',
        kind: 'boolean',
        defaultValue: 'false',
        range: 'true / false',
        description:
          'Say a short backchannel ("Hmm", "Okay") if the AI is slow to start replying. Fast replies get no filler.',
      },
      {
        key: 'thinking_delay_ms',
        label: 'Thinking filler delay (ms)',
        kind: 'number',
        min: 0,
        max: 5000,
        step: 50,
        requires: 'thinking',
        defaultValue: '800',
        range: '0 – 5000',
        description: 'How long to wait for the reply before saying the thinking filler. Lower plays it more often.',
      },
      {
        key: 'thinking_phrases',
        label: 'Thinking phrases',
        kind: 'phrases',
        requires: 'thinking',
        builtInPhrases: BUILT_IN_THINKING_PHRASES,
        defaultValue: 'built-in',
        range: '{ "en": ["Hmm"] }',
        description:
          'Optional. Your own thinking phrases per language code. Languages you leave out keep the built-in phrases (en, hi, ta, te, ml, kn).',
      },
      {
        key: 'before_tool_call',
        label: 'Say a phrase before tool calls',
        kind: 'boolean',
        defaultValue: 'false',
        range: 'true / false',
        description: 'Say a short phrase ("One moment please") before running a tool that may take a while.',
      },
      {
        key: 'tool_call_phrases',
        label: 'Tool-call phrases',
        kind: 'phrases',
        requires: 'before_tool_call',
        builtInPhrases: BUILT_IN_TOOL_CALL_PHRASES,
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
        label: 'Let the bot end the call',
        kind: 'boolean',
        defaultValue: 'false',
        range: 'true / false',
        description:
          'Turn on to let the AI end the call after the user says goodbye or that they are done. A "thank you" in the middle of the conversation does not end it.',
      },
      {
        key: 'farewell_message',
        label: 'Farewell message',
        kind: 'text',
        requires: 'enabled',
        defaultValue: 'Thank you for using our service! Goodbye!',
        range: 'text',
        description:
          'What the bot says before hanging up, unless the AI chooses its own goodbye. Only used when enabled.',
      },
    ],
  },
];

export const isPlainObject = (value: unknown): value is Record<string, unknown> =>
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
