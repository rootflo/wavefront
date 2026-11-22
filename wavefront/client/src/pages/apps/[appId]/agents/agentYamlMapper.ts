/**
 * Pure mapping between the agent YAML and the agent dialogs' form.
 *
 * The YAML is the source of truth. The form is derived from it (yamlToForm), and a form edit patches only
 * the YAML keys of the fields the user changed (patchYamlFromForm). Keys the form does not know about
 * (provider-specific model settings, max_retries, parser, examples, ...) are never touched.
 */
import yaml, { type DumpOptions } from 'js-yaml';
import type { AgentFormValues } from './schemas';

type YamlObject = Record<string, unknown>;

/** Form values that live in the agent YAML (everything except the YAML text itself). */
export type AgentYamlFormValues = Omit<AgentFormValues, 'yamlContent'>;
export type AgentYamlField = keyof AgentYamlFormValues;

export const ROOTFLO_PROVIDER = 'rootflo';

export const EMPTY_AGENT_FORM_VALUES: AgentYamlFormValues = {
  agentName: '',
  role: '',
  job: '',
  description: '',
  tags: '',
  actAs: '',
  modelId: '',
  temperature: null,
  maxTokens: null,
  reasoningPattern: '',
  topP: null,
  topK: null,
  frequencyPenalty: null,
  presencePenalty: null,
  seed: null,
};

const AGENT_YAML_FIELDS = new Set<string>(Object.keys(EMPTY_AGENT_FORM_VALUES));

export const isAgentYamlField = (name: string): name is AgentYamlField => AGENT_YAML_FIELDS.has(name);

// Form field -> key under agent.settings (flo_ai SettingsModel).
const SETTINGS_KEYS: Partial<Record<AgentYamlField, string>> = {
  temperature: 'temperature',
  maxTokens: 'max_tokens',
  reasoningPattern: 'reasoning_pattern',
  topP: 'top_p',
  topK: 'top_k',
  frequencyPenalty: 'frequency_penalty',
  presencePenalty: 'presence_penalty',
  seed: 'seed',
};

// Model keys that only mean something for a specific provider (flo_ai LLMConfigModel).
const PROVIDER_SPECIFIC_MODEL_KEYS = new Set([
  'name',
  'base_url',
  'api_key',
  'project',
  'location',
  'azure_endpoint',
  'azure_api_version',
]);

// Keys flo_ai's LLMConfigModel requires per provider.
const MODEL_REQUIRED_KEYS: Record<string, readonly string[]> = {
  openai: ['name'],
  anthropic: ['name'],
  claude: ['name'],
  gemini: ['name'],
  google: ['name'],
  ollama: ['name'],
  vertexai: ['name', 'project', 'base_url'],
  rootflo: ['model_id'],
  openai_vllm: ['name', 'base_url', 'api_key'],
  azure_openai: ['name'],
};

// lineWidth -1 keeps long prompts on one line instead of folding them.
const DUMP_OPTIONS: DumpOptions = { lineWidth: -1, noRefs: true };

const isObject = (value: unknown): value is YamlObject =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const asText = (value: unknown): string => {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return '';
};

const asNumber = (value: unknown): number | null => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

const isSameValue = (a: unknown, b: unknown): boolean => a === b || JSON.stringify(a) === JSON.stringify(b);

type ParsedAgentYaml = { ok: true; doc: YamlObject & { agent: YamlObject } } | { ok: false; error: string };

const parseAgentYaml = (yamlText: string): ParsedAgentYaml => {
  let doc: unknown;
  try {
    doc = yaml.load(yamlText);
  } catch (error) {
    if (error instanceof yaml.YAMLException) {
      return { ok: false, error: `Invalid YAML: ${error.reason} (line ${error.mark.line + 1})` };
    }
    return { ok: false, error: `Invalid YAML: ${error instanceof Error ? error.message : String(error)}` };
  }
  if (!isObject(doc) || !isObject(doc.agent)) {
    return { ok: false, error: 'The YAML must contain an "agent" section' };
  }
  return { ok: true, doc: doc as YamlObject & { agent: YamlObject } };
};

const dumpAgentYaml = (doc: YamlObject): string => yaml.dump(doc, DUMP_OPTIONS);

/** Sets `key` to `value`, or deletes it when `value` is undefined. Returns whether anything changed. */
const setKey = (target: YamlObject, key: string, value: unknown): boolean => {
  if (value === undefined) {
    if (!(key in target)) return false;
    delete target[key];
    return true;
  }
  if (key in target && isSameValue(target[key], value)) return false;
  target[key] = value;
  return true;
};

/** setKey on `parent[section]`, creating the section on write and removing it once empty. */
const setSectionKey = (parent: YamlObject, section: string, key: string, value: unknown): boolean => {
  const current = isObject(parent[section]) ? (parent[section] as YamlObject) : undefined;
  if (value === undefined) {
    if (!current || !setKey(current, key, undefined)) return false;
    if (Object.keys(current).length === 0) delete parent[section];
    return true;
  }
  const target = current ?? {};
  if (!setKey(target, key, value)) return false;
  parent[section] = target;
  return true;
};

const textOrUndefined = (value: string | undefined | null): string | undefined =>
  value != null && value.trim() !== '' ? value : undefined;

const parseTags = (tags: string | undefined): string[] | undefined => {
  const list = (tags ?? '')
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean);
  return list.length > 0 ? list : undefined;
};

const isRootfloModel = (model: YamlObject | undefined): boolean => {
  const provider = model ? asText(model.provider) : '';
  return !provider || provider === ROOTFLO_PROVIDER;
};

/** Points a RootFlo (or not yet configured) model block at `modelId`. Other providers are left alone. */
const patchModelId = (agent: YamlObject, modelId: string): boolean => {
  const model = isObject(agent.model) ? (agent.model as YamlObject) : undefined;
  // The RootFlo picker never rewrites another provider's block; switching is the explicit switchModelToRootflo.
  if (!isRootfloModel(model)) return false;
  const target = model ?? {};
  let changed = setKey(target, 'provider', ROOTFLO_PROVIDER);
  changed = setKey(target, 'model_id', modelId) || changed;
  agent.model = target;
  return changed;
};

const applyField = (
  doc: YamlObject,
  agent: YamlObject,
  field: AgentYamlField,
  values: Partial<AgentYamlFormValues>
): boolean => {
  const settingsKey = SETTINGS_KEYS[field];
  if (settingsKey) {
    const value = values[field];
    const next = typeof value === 'number' ? value : textOrUndefined(typeof value === 'string' ? value : undefined);
    return setSectionKey(agent, 'settings', settingsKey, next);
  }

  switch (field) {
    case 'agentName':
      return setKey(agent, 'name', textOrUndefined(values.agentName));
    case 'role':
      return setKey(agent, 'role', textOrUndefined(values.role));
    case 'job': {
      // flo_ai accepts `prompt` as an alias for `job`; keep writing to whichever key the YAML uses.
      const key = 'job' in agent || !('prompt' in agent) ? 'job' : 'prompt';
      return setKey(agent, key, textOrUndefined(values.job));
    }
    case 'actAs':
      return setKey(agent, 'act_as', textOrUndefined(values.actAs));
    case 'description':
      return setSectionKey(doc, 'metadata', 'description', textOrUndefined(values.description));
    case 'tags':
      return setSectionKey(doc, 'metadata', 'tags', parseTags(values.tags));
    case 'modelId':
      return patchModelId(agent, values.modelId ?? '');
    default:
      return false;
  }
};

export type AgentYamlToFormResult = { ok: true; values: AgentYamlFormValues } | { ok: false; error: string };

/** Derives every form field from the YAML. Missing keys become empty values, so nothing stale survives. */
export const yamlToForm = (yamlText: string): AgentYamlToFormResult => {
  const parsed = parseAgentYaml(yamlText);
  if (!parsed.ok) return parsed;

  const { agent } = parsed.doc;
  const metadata = isObject(parsed.doc.metadata) ? parsed.doc.metadata : {};
  const model = isObject(agent.model) ? agent.model : undefined;
  const settings = isObject(agent.settings) ? agent.settings : {};

  return {
    ok: true,
    values: {
      agentName: asText(agent.name),
      role: asText(agent.role),
      job: asText(agent.job) || asText(agent.prompt),
      description: asText(metadata.description),
      tags: Array.isArray(metadata.tags) ? metadata.tags.map(asText).filter(Boolean).join(', ') : asText(metadata.tags),
      actAs: asText(agent.act_as),
      modelId: model && isRootfloModel(model) ? asText(model.model_id) : '',
      temperature: asNumber(settings.temperature),
      maxTokens: asNumber(settings.max_tokens),
      reasoningPattern: asText(settings.reasoning_pattern),
      topP: asNumber(settings.top_p),
      topK: asNumber(settings.top_k),
      frequencyPenalty: asNumber(settings.frequency_penalty),
      presencePenalty: asNumber(settings.presence_penalty),
      seed: asNumber(settings.seed),
    },
  };
};

/**
 * Patches the YAML keys behind `fields` with their form values and returns the new YAML text.
 * Returns `existingYamlText` unchanged (same formatting and comments) when nothing actually changed
 * or when the YAML cannot be parsed.
 */
export const patchYamlFromForm = (
  existingYamlText: string,
  values: Partial<AgentYamlFormValues>,
  fields: Iterable<AgentYamlField>
): string => {
  const parsed = parseAgentYaml(existingYamlText);
  if (!parsed.ok) return existingYamlText;

  let changed = false;
  for (const field of fields) {
    changed = applyField(parsed.doc, parsed.doc.agent, field, values) || changed;
  }
  return changed ? dumpAgentYaml(parsed.doc) : existingYamlText;
};

export interface AgentModelInfo {
  provider: string;
  name: string;
  modelId: string;
}

/** The agent's model block as configured in YAML, or null when the YAML cannot be parsed. */
export const getAgentModelInfo = (yamlText: string): AgentModelInfo | null => {
  const parsed = parseAgentYaml(yamlText);
  if (!parsed.ok) return null;
  const model = isObject(parsed.doc.agent.model) ? parsed.doc.agent.model : {};
  return { provider: asText(model.provider), name: asText(model.name), modelId: asText(model.model_id) };
};

/**
 * Explicit user action: replace the model block with an (unselected) RootFlo model. Keys specific to the
 * previous provider are dropped because RootFlo would misread them (e.g. base_url); generic keys
 * (temperature, max_tokens, timeout) and unknown keys are kept.
 */
export const switchModelToRootflo = (yamlText: string): string => {
  const parsed = parseAgentYaml(yamlText);
  if (!parsed.ok) return yamlText;
  const { agent } = parsed.doc;
  const model = isObject(agent.model) ? agent.model : {};
  const next: YamlObject = { provider: ROOTFLO_PROVIDER, model_id: '' };
  for (const [key, value] of Object.entries(model)) {
    if (key in next || PROVIDER_SPECIFIC_MODEL_KEYS.has(key)) continue;
    next[key] = value;
  }
  agent.model = next;
  return dumpAgentYaml(parsed.doc);
};

/**
 * Create dialog: keeps agent.name and metadata.name in step with the agent id. A name is only replaced while
 * it is empty or still the value derived from the previous id, so a name customised in YAML is kept.
 */
export const syncAgentIdentity = (yamlText: string, agentId: string, previousAgentId: string): string => {
  const parsed = parseAgentYaml(yamlText);
  if (!parsed.ok) return yamlText;
  const { doc } = parsed;
  const id = agentId.trim();
  const previousId = previousAgentId.trim();

  let changed = false;
  const currentName = asText(doc.agent.name);
  if (!currentName || currentName === previousId) {
    changed = setKey(doc.agent, 'name', id || undefined) || changed;
  }
  const metadataName = isObject(doc.metadata) ? asText(doc.metadata.name) : '';
  if (!metadataName || metadataName === `${previousId}-agent`) {
    changed = setSectionKey(doc, 'metadata', 'name', id ? `${id}-agent` : undefined) || changed;
  }
  return changed ? dumpAgentYaml(doc) : yamlText;
};

/** Whether two YAML texts describe the same document, ignoring comments and formatting. */
export const isSameYamlDocument = (a: string, b: string): boolean => {
  if (a === b) return true;
  try {
    return isSameValue(yaml.load(a), yaml.load(b));
  } catch {
    return false;
  }
};

const toolEntryName = (entry: unknown): string => (isObject(entry) ? asText(entry.name) : asText(entry));

/** Names of the tools referenced in agent.tools, or null when the YAML cannot be parsed. */
export const getAgentToolNames = (yamlText: string): Set<string> | null => {
  const parsed = parseAgentYaml(yamlText);
  if (!parsed.ok) return null;
  const tools = Array.isArray(parsed.doc.agent.tools) ? parsed.doc.agent.tools : [];
  return new Set(tools.map(toolEntryName).filter(Boolean));
};

export interface AgentToolOption {
  name: string;
  description?: string;
  prefilledParams?: Record<string, string>;
}

/**
 * Adds or removes one tool in agent.tools. Other entries, including their prefilled_params and overrides,
 * are kept as they are.
 */
export const setAgentTool = (
  yamlText: string,
  tool: AgentToolOption,
  enabled: boolean
): { ok: true; yaml: string } | { ok: false; error: string } => {
  const parsed = parseAgentYaml(yamlText);
  if (!parsed.ok) return parsed;
  const { agent } = parsed.doc;
  const tools: unknown[] = Array.isArray(agent.tools) ? agent.tools : [];
  const isPresent = tools.some((entry) => toolEntryName(entry) === tool.name);
  if (isPresent === enabled) return { ok: true, yaml: yamlText };

  if (enabled) {
    const entry: YamlObject = { name: tool.name };
    if (tool.prefilledParams && Object.keys(tool.prefilledParams).length > 0) {
      entry.prefilled_params = tool.prefilledParams;
    }
    entry.name_override = tool.name;
    if (tool.description) entry.description_override = tool.description;
    agent.tools = [...tools, entry];
  } else {
    const remaining = tools.filter((entry) => toolEntryName(entry) !== tool.name);
    if (remaining.length > 0) agent.tools = remaining;
    else delete agent.tools;
  }
  return { ok: true, yaml: dumpAgentYaml(parsed.doc) };
};

export interface AgentYamlIssue {
  field: 'yamlContent' | 'modelId';
  message: string;
}

/**
 * Checks the parts of the YAML the server validates but the form fields do not represent: the model block
 * (flo_ai LLMConfigModel provider requirements) and agent.name. job/prompt and settings are covered by the
 * form schema, whose values always mirror the YAML.
 */
export const validateAgentYaml = (yamlText: string): AgentYamlIssue[] => {
  const parsed = parseAgentYaml(yamlText);
  if (!parsed.ok) return [{ field: 'yamlContent', message: parsed.error }];

  const { agent } = parsed.doc;
  const issues: AgentYamlIssue[] = [];
  if (!asText(agent.name).trim()) {
    issues.push({ field: 'yamlContent', message: 'agent.name is required' });
  }

  const model = isObject(agent.model) ? agent.model : undefined;
  const provider = model ? asText(model.provider) : '';
  const requiredKeys = MODEL_REQUIRED_KEYS[provider];
  if (!model || !provider) {
    issues.push({ field: 'modelId', message: 'Select an LLM model' });
  } else if (!requiredKeys) {
    issues.push({ field: 'yamlContent', message: `Unsupported model provider "${provider}"` });
  } else {
    const missing = requiredKeys.filter((key) => !asText(model[key]).trim());
    if (missing.length > 0 && provider === ROOTFLO_PROVIDER) {
      issues.push({ field: 'modelId', message: 'Select an LLM model' });
    } else if (missing.length > 0) {
      issues.push({
        field: 'yamlContent',
        message: `The ${provider} model requires ${missing.map((key) => `"${key}"`).join(', ')} in agent.model`,
      });
    }
  }
  return issues;
};
