/**
 * Popular models per provider, and which settings each one accepts.
 *
 * Checked against the providers' docs in October 2026: OpenAI and Azure
 * OpenAI reasoning-model pages, Gemini thinking docs, GroqCloud models,
 * Anthropic models overview. Sending a setting a model rejects fails the whole
 * request (a 400), so a model only lists what it is documented to take.
 * A model not listed here gets every setting its provider has.
 */

import {
  getProviderConfig,
  type InferenceEngineType,
  type ParameterConfig,
  type ParameterOption,
} from '@app/config/llm-providers';

export type ModelTag = 'voice' | 'reasoning' | 'fast' | 'preview' | 'legacy';

export interface ModelPreset {
  id: string;
  label: string;
  description: string;
  tags?: ModelTag[];
  /** Setting keys (from the provider config) this model accepts. */
  params: string[];
  /** Per-model narrowing of a setting: the values it takes, its default, its range. */
  overrides?: Record<string, Partial<ParameterConfig>>;
  /** Something to know before using the model (shown with the settings). */
  note?: string;
}

export interface ModelGroup {
  label: string;
  models: ModelPreset[];
}

const efforts = (values: string[], defaultValue?: string): Partial<ParameterConfig> => ({
  options: values.map((value) => ({ value, label: EFFORT_LABELS[value] ?? value })),
  default: defaultValue,
});

const EFFORT_LABELS: Record<string, string> = {
  none: 'None',
  minimal: 'Minimal',
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  xhigh: 'Extra high',
};

const maxOut = (max: number): Partial<ParameterConfig> => ({ max });

// ---- OpenAI / Azure OpenAI ----------------------------------------------------------

// Non-reasoning chat models take the full sampling set.
const OPENAI_SAMPLING = ['temperature', 'top_p', 'frequency_penalty', 'presence_penalty', 'seed'];
// Reasoning models reject temperature, top_p, penalties and logprobs (Azure reasoning docs).
const OPENAI_REASONING = ['reasoning_effort', 'max_completion_tokens'];
// Models with a None effort take temperature and top_p only while effort is None:
// OpenAI documents it for GPT-5.1, 5.2, 5.4, GPT-6 Sol and Luna ("when reasoning
// effort is not none, remove temperature, top_p"). Any other effort fails the request,
// and on a model whose default effort isn't None, None has to be chosen explicitly.
// GPT-5.5 and 5.6 aren't covered by that note; they get the same rule as the
// family, which at worst hides a setting they would have taken.
const OPENAI_REASONING_WITH_NONE = [...OPENAI_REASONING, 'temperature', 'top_p'];
const WHEN_EFFORT_NONE = { key: 'reasoning_effort', equals: 'none' };
const SAMPLING_WHEN_EFFORT_NONE: Record<string, Partial<ParameterConfig>> = {
  temperature: { activeWhen: WHEN_EFFORT_NONE },
  top_p: { activeWhen: WHEN_EFFORT_NONE },
};

const GPT5_EFFORTS = ['none', 'low', 'medium', 'high', 'xhigh'];
const TOOLS_NEED_NONE =
  'Function tools on Chat Completions only work with reasoning effort None, and this model defaults to Medium. Voice agents always send tools: set it to None.';
// Voice agents and flo_ai both call Chat Completions, with tools.
const TOOLS_NEED_RESPONSES =
  'Tool calling on this model needs the Responses API; Chat Completions only serves requests without tools. Voice agents and tool-using chatbots and agents will fail with it.';

const gpt6Astra: ModelPreset = {
  id: 'gpt-6-astra',
  label: 'GPT-6 Astra',
  description: 'Most capable; not for voice or tool use',
  tags: ['reasoning'],
  // No None effort, so temperature and top_p are never accepted (OpenAI GPT-6 guide)
  params: OPENAI_REASONING,
  overrides: {
    reasoning_effort: efforts(['low', 'medium', 'high', 'xhigh'], 'medium'),
    max_completion_tokens: maxOut(128000),
  },
  note: TOOLS_NEED_RESPONSES,
};

const gpt61Sol: ModelPreset = {
  id: 'gpt-6.1-sol',
  label: 'GPT-6.1 Sol',
  description: 'Near-Astra quality; not for voice or tool use',
  tags: ['reasoning'],
  params: OPENAI_REASONING,
  overrides: {
    reasoning_effort: efforts(['low', 'medium', 'high', 'xhigh'], 'medium'),
    max_completion_tokens: maxOut(128000),
  },
  note: TOOLS_NEED_RESPONSES,
};

const gpt6Luna: ModelPreset = {
  id: 'gpt-6-luna',
  label: 'GPT-6 Luna',
  description: 'Fast, low-cost GPT-6 for high volume',
  tags: ['reasoning', 'voice'],
  params: OPENAI_REASONING_WITH_NONE,
  overrides: {
    reasoning_effort: efforts(GPT5_EFFORTS, 'medium'),
    max_completion_tokens: maxOut(128000),
    ...SAMPLING_WHEN_EFFORT_NONE,
  },
  note: TOOLS_NEED_NONE,
};

const gpt54 = (id: string, label: string, description: string, tags: ModelTag[]): ModelPreset => ({
  id,
  label,
  description,
  tags: ['reasoning', ...tags],
  params: OPENAI_REASONING_WITH_NONE,
  overrides: {
    reasoning_effort: efforts(GPT5_EFFORTS, 'none'),
    max_completion_tokens: maxOut(128000),
    ...SAMPLING_WHEN_EFFORT_NONE,
  },
});

const gpt4 = (id: string, label: string, description: string, max: number, tags: ModelTag[] = []): ModelPreset => ({
  id,
  label,
  description,
  tags,
  params: [...OPENAI_SAMPLING, 'max_completion_tokens', 'service_tier'],
  overrides: { max_completion_tokens: maxOut(max) },
});

const OPENAI_MODELS: ModelGroup[] = [
  { label: 'GPT-6', models: [gpt6Luna, gpt61Sol, gpt6Astra] },
  {
    label: 'GPT-5.4',
    models: [
      gpt54('gpt-5.4-nano', 'GPT-5.4 nano', 'Fastest GPT-5.4; good for voice', ['voice', 'fast']),
      gpt54('gpt-5.4-mini', 'GPT-5.4 mini', 'Balanced speed and quality', ['voice']),
      gpt54('gpt-5.4', 'GPT-5.4', 'Full GPT-5.4', []),
    ],
  },
  {
    label: 'GPT-4.1 / GPT-4o (no reasoning)',
    models: [
      gpt4('gpt-4.1-mini', 'GPT-4.1 mini', 'Fast, no reasoning step', 32768, ['voice', 'fast']),
      gpt4('gpt-4.1-nano', 'GPT-4.1 nano', 'Smallest GPT-4.1', 32768, ['fast']),
      gpt4('gpt-4.1', 'GPT-4.1', 'Strong non-reasoning model', 32768),
      gpt4('gpt-4o-mini', 'GPT-4o mini', 'Older small model', 16384, ['legacy']),
      gpt4('gpt-4o', 'GPT-4o', 'Older flagship', 16384, ['legacy']),
    ],
  },
];

/** Azure has no service tier setting; everything else matches OpenAI's model rules. */
const azure = (preset: ModelPreset): ModelPreset => ({
  ...preset,
  params: preset.params.filter((p) => p !== 'service_tier'),
});

const gpt56 = (id: string, label: string, description: string, tags: ModelTag[] = []): ModelPreset => ({
  id,
  label,
  description,
  tags: ['reasoning', ...tags],
  params: OPENAI_REASONING_WITH_NONE,
  overrides: {
    reasoning_effort: efforts(GPT5_EFFORTS, 'medium'),
    max_completion_tokens: maxOut(128000),
    ...SAMPLING_WHEN_EFFORT_NONE,
  },
  note: TOOLS_NEED_NONE,
});

const gpt5Original = (id: string, label: string, description: string, tags: ModelTag[] = []): ModelPreset => ({
  id,
  label,
  description,
  tags: ['reasoning', 'legacy', ...tags],
  params: OPENAI_REASONING,
  overrides: {
    reasoning_effort: efforts(['minimal', 'low', 'medium', 'high'], 'medium'),
    max_completion_tokens: maxOut(128000),
  },
  note: 'Defaults to Medium effort. Set Minimal for the fastest replies.',
});

const AZURE_MODELS: ModelGroup[] = [
  {
    label: 'GPT-6',
    models: [
      gpt6Luna,
      gpt61Sol,
      { ...gpt6Luna, id: 'gpt-6-sol', label: 'GPT-6 Sol', description: 'Previous Sol release', tags: ['reasoning'] },
      gpt6Astra,
    ],
  },
  {
    label: 'GPT-5.6',
    models: [
      gpt56('gpt-5.6-luna', 'GPT-5.6 Luna', 'Fastest GPT-5.6', ['voice']),
      gpt56('gpt-5.6-terra', 'GPT-5.6 Terra', 'Balanced GPT-5.6'),
      gpt56('gpt-5.6-sol', 'GPT-5.6 Sol', 'Most capable GPT-5.6'),
    ],
  },
  {
    label: 'GPT-5.4 / 5.5',
    models: [
      gpt54('gpt-5.4-nano', 'GPT-5.4 nano', 'Fastest GPT-5.4; good for voice', ['voice', 'fast']),
      gpt54('gpt-5.4-mini', 'GPT-5.4 mini', 'Balanced speed and quality', ['voice']),
      gpt54('gpt-5.4', 'GPT-5.4', 'Full GPT-5.4', []),
      {
        ...gpt54('gpt-5.5', 'GPT-5.5', 'Newer full model; defaults to Medium effort', []),
        overrides: {
          reasoning_effort: efforts(GPT5_EFFORTS, 'medium'),
          max_completion_tokens: maxOut(128000),
          ...SAMPLING_WHEN_EFFORT_NONE,
        },
      },
    ],
  },
  {
    label: 'GPT-5 / 5.1 / 5.2',
    models: [
      {
        id: 'gpt-5.2',
        label: 'GPT-5.2',
        description: 'Earlier GPT-5 release',
        tags: ['reasoning', 'legacy'],
        params: OPENAI_REASONING_WITH_NONE,
        overrides: {
          reasoning_effort: efforts(GPT5_EFFORTS, 'none'),
          max_completion_tokens: maxOut(128000),
          ...SAMPLING_WHEN_EFFORT_NONE,
        },
      },
      {
        id: 'gpt-5.1',
        label: 'GPT-5.1',
        description: 'Earlier GPT-5 release',
        tags: ['reasoning', 'legacy'],
        params: OPENAI_REASONING_WITH_NONE,
        overrides: {
          reasoning_effort: efforts(['none', 'low', 'medium', 'high'], 'none'),
          max_completion_tokens: maxOut(128000),
          ...SAMPLING_WHEN_EFFORT_NONE,
        },
      },
      gpt5Original('gpt-5-nano', 'GPT-5 nano', 'Original GPT-5, smallest'),
      gpt5Original('gpt-5-mini', 'GPT-5 mini', 'Original GPT-5, small'),
      gpt5Original('gpt-5', 'GPT-5', 'Original GPT-5'),
    ],
  },
  {
    label: 'GPT-4.1 / GPT-4o (no reasoning)',
    models: OPENAI_MODELS[2]!.models.map(azure),
  },
  {
    label: 'o-series',
    models: [
      {
        id: 'o4-mini',
        label: 'o4-mini',
        description: 'Older small reasoning model',
        tags: ['reasoning', 'legacy'],
        params: OPENAI_REASONING,
        overrides: {
          reasoning_effort: efforts(['low', 'medium', 'high'], 'medium'),
          max_completion_tokens: maxOut(100000),
        },
      },
      {
        id: 'o3',
        label: 'o3',
        description: 'Older reasoning model',
        tags: ['reasoning', 'legacy'],
        params: OPENAI_REASONING,
        overrides: {
          reasoning_effort: efforts(['low', 'medium', 'high'], 'medium'),
          max_completion_tokens: maxOut(100000),
        },
      },
    ],
  },
];

// ---- Gemini --------------------------------------------------------------------------

// Gemini 3+ takes a thinking level; 2.5 takes a token budget (sending the other one is a 400).
const GEMINI_SAMPLING = ['temperature', 'max_tokens', 'top_p', 'top_k'];

const gemini3 = (
  id: string,
  label: string,
  description: string,
  levels: string[],
  defaultLevel: string,
  tags: ModelTag[] = []
): ModelPreset => ({
  id,
  label,
  description,
  tags: ['reasoning', ...tags],
  params: ['thinking_level', ...GEMINI_SAMPLING],
  overrides: { thinking_level: efforts(levels, defaultLevel) },
});

const gemini25 = (
  id: string,
  label: string,
  description: string,
  budget: Partial<ParameterConfig>,
  note: string
): ModelPreset => ({
  id,
  label,
  description,
  tags: ['legacy'],
  params: ['thinking_budget', ...GEMINI_SAMPLING],
  overrides: { thinking_budget: budget },
  note,
});

const GEMINI_MODELS: ModelGroup[] = [
  {
    label: 'Gemini 3 and later',
    models: [
      gemini3(
        'gemini-3.5-flash-lite',
        'Gemini 3.5 Flash-Lite',
        'Fastest; thinks minimally by default',
        ['minimal', 'low', 'medium', 'high'],
        'minimal',
        ['voice', 'fast']
      ),
      gemini3(
        'gemini-3.6-flash',
        'Gemini 3.6 Flash',
        'Fast and capable',
        ['minimal', 'low', 'medium', 'high'],
        'medium',
        ['voice']
      ),
      gemini3('gemini-3.8-flash', 'Gemini 3.8 Flash', 'Latest Flash', ['low', 'medium', 'high'], 'medium', ['voice']),
      gemini3('gemini-4-argon', 'Gemini 4 Argon', 'Most capable', ['low', 'medium', 'high'], 'medium'),
      gemini3(
        'gemini-3.1-pro-preview',
        'Gemini 3.1 Pro (preview)',
        'Pro tier preview',
        ['low', 'medium', 'high'],
        'high',
        ['preview']
      ),
      gemini3(
        'gemini-3-flash-preview',
        'Gemini 3 Flash (preview)',
        'Thinks at High by default',
        ['minimal', 'low', 'medium', 'high'],
        'high',
        ['preview']
      ),
    ],
  },
  {
    label: 'Gemini 2.5 (existing users only)',
    models: [
      gemini25(
        'gemini-2.5-flash',
        'Gemini 2.5 Flash',
        'Thinks by default',
        { min: 0, max: 24576 },
        'Set the thinking budget to 0 to turn thinking off for faster replies.'
      ),
      gemini25(
        'gemini-2.5-flash-lite',
        'Gemini 2.5 Flash-Lite',
        'No thinking by default',
        { min: 0, max: 24576 },
        'Thinking is off unless you give it a budget.'
      ),
      gemini25(
        'gemini-2.5-pro',
        'Gemini 2.5 Pro',
        'Always thinks',
        { min: 128, max: 32768 },
        'Thinking cannot be turned off; the lowest budget is 128.'
      ),
    ],
  },
];

// ---- Groq ----------------------------------------------------------------------------

const GROQ_SAMPLING = ['temperature', 'top_p', 'frequency_penalty', 'presence_penalty', 'seed', 'service_tier'];

const GROQ_MODELS: ModelGroup[] = [
  {
    label: 'Production',
    models: [
      {
        id: 'openai/gpt-oss-20b',
        label: 'GPT-OSS 20B',
        description: 'Very fast open-weight reasoning model',
        tags: ['reasoning', 'voice', 'fast'],
        params: ['reasoning_effort', 'max_completion_tokens', 'temperature', 'top_p', 'seed', 'service_tier'],
        overrides: { reasoning_effort: efforts(['low', 'medium', 'high'], 'medium') },
        note: 'Set reasoning effort to Low for the fastest replies.',
      },
      {
        id: 'openai/gpt-oss-120b',
        label: 'GPT-OSS 120B',
        description: 'Larger open-weight reasoning model',
        tags: ['reasoning'],
        params: ['reasoning_effort', 'max_completion_tokens', 'temperature', 'top_p', 'seed', 'service_tier'],
        overrides: { reasoning_effort: efforts(['low', 'medium', 'high'], 'medium') },
      },
      {
        id: 'llama-3.3-70b-versatile',
        label: 'Llama 3.3 70B',
        description: 'No reasoning step',
        tags: ['voice'],
        params: [...GROQ_SAMPLING, 'max_completion_tokens'],
        overrides: { max_completion_tokens: maxOut(32768) },
      },
      {
        id: 'llama-3.1-8b-instant',
        label: 'Llama 3.1 8B Instant',
        description: 'Smallest and fastest',
        tags: ['fast'],
        params: [...GROQ_SAMPLING, 'max_completion_tokens'],
        overrides: { max_completion_tokens: maxOut(131072) },
      },
    ],
  },
  {
    label: 'Preview',
    models: [
      {
        id: 'qwen/qwen3.8-27b',
        label: 'Qwen 3.8 27B',
        description: 'Preview model',
        tags: ['preview'],
        params: ['temperature', 'top_p', 'max_completion_tokens', 'seed'],
      },
    ],
  },
];

// ---- Anthropic (chatbots and agents) -------------------------------------------------

// Claude 5.x, Opus 4.7/4.8 and Sonnet 5 reject temperature / top_p / top_k (a 400);
// Sonnet 4.6 and Haiku 4.5 still take them.
const claudeNoSampling = (id: string, label: string, description: string, tags: ModelTag[] = []): ModelPreset => ({
  id,
  label,
  description,
  tags,
  params: ['max_tokens'],
  overrides: { max_tokens: maxOut(128000) },
  note: 'This model rejects temperature, top P and top K, so they are hidden.',
});

const ANTHROPIC_MODELS: ModelGroup[] = [
  {
    label: 'Claude 5',
    models: [
      claudeNoSampling('claude-opus-5-5', 'Claude Opus 5.5', 'Most capable Opus'),
      claudeNoSampling('claude-sonnet-5-5', 'Claude Sonnet 5.5', 'Speed and capability for everyday work'),
      claudeNoSampling('claude-haiku-5-5', 'Claude Haiku 5.5', 'Fastest and cheapest', ['fast']),
      claudeNoSampling('claude-fable-5-1', 'Claude Fable 5.1', 'Most capable Claude; long, deep tasks'),
    ],
  },
  {
    label: 'Earlier',
    models: [
      claudeNoSampling('claude-opus-4-8', 'Claude Opus 4.8', 'Previous Opus', ['legacy']),
      {
        id: 'claude-sonnet-4-6',
        label: 'Claude Sonnet 4.6',
        description: 'Previous Sonnet',
        tags: ['legacy'],
        params: ['temperature', 'max_tokens', 'top_p', 'top_k'],
        overrides: { max_tokens: maxOut(128000) },
      },
      {
        id: 'claude-haiku-4-5',
        label: 'Claude Haiku 4.5',
        description: 'Previous Haiku',
        tags: ['legacy'],
        params: ['temperature', 'max_tokens', 'top_p', 'top_k'],
        overrides: { max_tokens: maxOut(64000) },
      },
    ],
  },
];

export const LLM_MODEL_CATALOG: Record<InferenceEngineType, ModelGroup[]> = {
  openai: OPENAI_MODELS,
  azure_openai: AZURE_MODELS,
  gemini: GEMINI_MODELS,
  groq: GROQ_MODELS,
  anthropic: ANTHROPIC_MODELS,
  ollama: [],
  vllm: [],
};

export function getModelGroups(provider: InferenceEngineType): ModelGroup[] {
  return LLM_MODEL_CATALOG[provider] ?? [];
}

/**
 * The model to pre-select when a provider is chosen: the first one tagged for
 * voice, else the first fast one, else the first listed. Empty when the provider
 * has no catalog (self-hosted: the model ID is typed in).
 */
export function getDefaultModelId(provider: InferenceEngineType): string {
  const models = getModelGroups(provider).flatMap((g) => g.models);
  return (
    (models.find((m) => m.tags?.includes('voice')) ?? models.find((m) => m.tags?.includes('fast')) ?? models[0])?.id ??
    ''
  );
}

/**
 * The catalog model a model ID refers to: the exact ID, otherwise the longest
 * catalog ID it contains. That covers dated snapshots (gpt-4.1-2025-04-14) and
 * Azure deployments named after their model (prod-gpt-5.4-nano).
 */
export function findModelPreset(provider: InferenceEngineType, modelId: string | undefined): ModelPreset | null {
  const id = modelId?.trim().toLowerCase();
  if (!id) return null;
  const models = getModelGroups(provider).flatMap((g) => g.models);
  const exact = models.find((m) => m.id === id);
  if (exact) return exact;
  let best: ModelPreset | null = null;
  for (const m of models) {
    if (containsModelId(id, m.id) && (!best || m.id.length > best.id.length)) best = m;
  }
  return best;
}

// A whole-name match: "gpt-5" must not match inside "gpt-5.4-nano", nor "o3" inside "pro3".
function containsModelId(haystack: string, needle: string): boolean {
  const partOfName = /[a-z0-9.]/;
  for (let at = haystack.indexOf(needle); at !== -1; at = haystack.indexOf(needle, at + 1)) {
    const before = haystack[at - 1];
    const after = haystack[at + needle.length];
    if ((before === undefined || !partOfName.test(before)) && (after === undefined || !partOfName.test(after))) {
      return true;
    }
  }
  return false;
}

/**
 * The settings to show for a model, narrowed by its catalog entry. An unknown
 * model gets every provider setting, since nothing says what it rejects.
 */
export function getModelParameters(
  provider: InferenceEngineType,
  modelId: string | undefined
): Array<[string, ParameterConfig]> {
  const all = getProviderConfig(provider)?.parameters ?? {};
  const preset = findModelPreset(provider, modelId);
  if (!preset) return Object.entries(all);
  return Object.entries(all)
    .filter(([key]) => preset.params.includes(key))
    .map(([key, config]) => [key, narrow(config, preset.overrides?.[key])]);
}

function narrow(config: ParameterConfig, override?: Partial<ParameterConfig>): ParameterConfig {
  if (!override) return config;
  // Keep the provider's labels for option values the override names.
  const options: ParameterOption[] | undefined = override.options?.map(
    (o) => config.options?.find((c) => String(c.value) === String(o.value)) ?? o
  );
  return { ...config, ...override, options: options ?? config.options };
}

/**
 * Saved parameters reduced to the ones this model accepts (for loading a
 * config into the form, and for saving it). Returns what was dropped too, so
 * the form can say so.
 */
/**
 * Whether a setting applies right now. A setting with `activeWhen` (temperature
 * on GPT-5.4, with reasoning effort None) needs the setting it depends on to have
 * that value; unset, the model's default effort counts.
 */
export function isParameterActive(
  config: ParameterConfig,
  modelParams: Array<[string, ParameterConfig]>,
  values: Record<string, unknown>
): boolean {
  const when = config.activeWhen;
  if (!when) return true;
  const chosen = values[when.key];
  const effective =
    chosen !== undefined && chosen !== null && chosen !== ''
      ? chosen
      : modelParams.find(([key]) => key === when.key)?.[1].default;
  return effective !== undefined && String(effective) === when.equals;
}

export function filterParameters(
  provider: InferenceEngineType,
  modelId: string | undefined,
  params: Record<string, unknown> | null | undefined
): { kept: Record<string, unknown>; dropped: string[] } {
  const allowed = new Map(getModelParameters(provider, modelId));
  const kept: Record<string, unknown> = {};
  const dropped: string[] = [];
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    const config = allowed.get(key);
    if (!config) {
      // api_version is Azure's connection setting, kept in parameters but not a model setting.
      if (key !== 'api_version') dropped.push(key);
      return;
    }
    if (config.type === 'select' && config.options && !config.options.some((o) => String(o.value) === String(value))) {
      dropped.push(key);
      return;
    }
    if (!isParameterActive(config, [...allowed], params ?? {})) {
      dropped.push(key);
      return;
    }
    kept[key] = value;
  });
  return { kept, dropped };
}

export function getParameterLabel(provider: InferenceEngineType, key: string): string {
  return getProviderConfig(provider)?.parameters[key]?.label ?? key.replace(/_/g, ' ');
}
