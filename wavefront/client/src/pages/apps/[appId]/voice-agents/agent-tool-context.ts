/**
 * Call context settings for one agent↔tool association: which tool arguments
 * the server fills in from the call, and whether the tool's answer can be
 * reused or fetched as the call starts. Stored in the association's
 * `config_overrides.context` (read by call_processing's context/bindings.py
 * and context/store.py); the rules here mirror the server's.
 */
import { ApiToolConfig, VoiceAgentTool } from '@app/types/tool';

/** Who fills an argument: the AI, or a value the server takes from the call. */
export type ArgumentSource = 'ai' | 'caller.phone' | 'call.id' | 'call.direction' | 'agent.id';

export const ARGUMENT_SOURCES: { value: ArgumentSource; label: string; example: string }[] = [
  { value: 'ai', label: 'The AI, from the conversation', example: 'asked or inferred during the call' },
  { value: 'caller.phone', label: "Caller's phone number", example: 'sent as +91XXXXXXXXXX' },
  { value: 'call.id', label: 'Call ID', example: "the telephony provider's call id" },
  { value: 'call.direction', label: 'Call direction', example: '"inbound" or "outbound"' },
  { value: 'agent.id', label: "This agent's ID", example: 'the voice agent id' },
];

const SERVER_SOURCES = new Set<string>(ARGUMENT_SOURCES.filter((s) => s.value !== 'ai').map((s) => s.value));

export interface ToolContextSettings {
  /** Argument name -> server source. Arguments not listed are filled by the AI. */
  bind: Record<string, Exclude<ArgumentSource, 'ai'>>;
  readOnly: boolean;
  prefetch: boolean;
}

export interface ToolArgument {
  name: string;
  description?: string;
  required: boolean;
}

type Overrides = Record<string, unknown> | undefined;

/** Who fills this argument now ('ai' unless the server is set to). */
export const argumentSource = (settings: Pick<ToolContextSettings, 'bind'>, arg: string): ArgumentSource =>
  settings.bind[arg] ?? 'ai';

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};

/** The tool's arguments, from its JSON-schema `parameter_schema`. */
export const toolArguments = (tool: Pick<VoiceAgentTool, 'parameter_schema'>): ToolArgument[] => {
  const schema = asRecord(tool.parameter_schema);
  const properties = asRecord(schema.properties);
  const required = new Set(Array.isArray(schema.required) ? schema.required.map(String) : []);
  return Object.entries(properties).map(([name, spec]) => {
    const description = asRecord(spec).description;
    return {
      name,
      description: typeof description === 'string' ? description : undefined,
      required: required.has(name),
    };
  });
};

export const readToolContext = (overrides: Overrides): ToolContextSettings => {
  const context = asRecord(asRecord(overrides).context);
  const bind: ToolContextSettings['bind'] = {};
  Object.entries(asRecord(context.bind)).forEach(([arg, source]) => {
    if (typeof source === 'string' && SERVER_SOURCES.has(source)) {
      bind[arg] = source as Exclude<ArgumentSource, 'ai'>;
    }
  });
  return { bind, readOnly: context.read_only === true, prefetch: context.prefetch === true };
};

/**
 * New `config_overrides` with these settings. Other override keys, and other
 * `context` keys (set by later features), are kept; empty settings are removed.
 */
export const writeToolContext = (overrides: Overrides, settings: ToolContextSettings): Record<string, unknown> => {
  const rest = { ...asRecord(overrides) };
  delete rest.context;
  const context: Record<string, unknown> = { ...asRecord(asRecord(overrides).context) };
  delete context.bind;
  delete context.read_only;
  delete context.prefetch;
  if (Object.keys(settings.bind).length > 0) context.bind = { ...settings.bind };
  if (settings.readOnly) context.read_only = true;
  if (settings.prefetch) context.prefetch = true;
  return Object.keys(context).length > 0 ? { ...rest, context } : rest;
};

/** The HTTP method the tool really uses (an association override wins). */
export const effectiveMethod = (tool: Pick<VoiceAgentTool, 'config'>, overrides: Overrides): string => {
  const override = asRecord(overrides).method;
  const method = typeof override === 'string' ? override : (tool.config as ApiToolConfig).method;
  return (method || 'POST').toUpperCase();
};

/** The server reuses a tool's answer within a call only when it is opted in like this. */
export const isReusedInCall = (method: string, settings: ToolContextSettings): boolean =>
  settings.readOnly || (settings.prefetch && method === 'GET');

/** Why the tool can't be fetched at call start, in plain words (empty = it can). */
export const prefetchBlockers = (
  args: ToolArgument[],
  method: string,
  settings: Pick<ToolContextSettings, 'bind' | 'readOnly'>
): string[] => {
  const blockers: string[] = [];
  const leftToAi = args.filter((a) => !settings.bind[a.name]).map((a) => a.name);
  if (leftToAi.length > 0) {
    blockers.push(
      `Before the call starts nobody has spoken yet, so every detail must be filled automatically. ` +
        `Still set to the AI: ${leftToAi.join(', ')}.`
    );
  }
  if (method !== 'GET' && !settings.readOnly) {
    blockers.push(
      `This tool sends a ${method} request, which may change data. ` +
        `Turn on "Only reads data" if it just looks something up.`
    );
  }
  return blockers;
};

const PHONE_NAME = /(phone|mobile|msisdn|contact_?(no|num|number)|cell)/i;
const CALL_ID_NAME = /call_?(id|sid|ref)/i;

/** A likely server source for an argument, from its name. */
export const suggestedSource = (arg: ToolArgument): Exclude<ArgumentSource, 'ai'> | undefined => {
  if (PHONE_NAME.test(arg.name)) return 'caller.phone';
  if (CALL_ID_NAME.test(arg.name)) return 'call.id';
  return undefined;
};

const SOURCE_PHRASES: Record<Exclude<ArgumentSource, 'ai'>, string> = {
  'caller.phone': "the caller's phone number",
  'call.id': 'the call ID',
  'call.direction': 'the call direction',
  'agent.id': "this agent's ID",
};

/** What happens on a phone call with these settings, one plain sentence per effect. */
export const describeOnCall = (method: string, settings: ToolContextSettings, canPrefetch: boolean): string[] => {
  const lines = Object.entries(settings.bind).map(
    ([arg, source]) =>
      `The server sends ${SOURCE_PHRASES[source]} as "${arg}". The AI doesn't see this detail and won't ask for it.`
  );
  if (settings.prefetch && canPrefetch) {
    lines.push('The lookup runs as the call starts, while the greeting plays, so the answer is ready when asked.');
  }
  if (isReusedInCall(method, { ...settings, prefetch: settings.prefetch && canPrefetch })) {
    lines.push('If the same lookup is needed again in this call, the saved answer is reused (kept for 15 minutes).');
  }
  if (lines.length === 0) {
    lines.push('Works as it does today: the AI fills every detail and the tool runs only when the AI calls it.');
  }
  return lines;
};

/** Short status for the tools list, or undefined when nothing is set. */
export const contextSummary = (
  tool: Pick<VoiceAgentTool, 'config' | 'parameter_schema'>,
  overrides: Overrides
): string | undefined => {
  const settings = readToolContext(overrides);
  const method = effectiveMethod(tool, overrides);
  if (settings.prefetch && prefetchBlockers(toolArguments(tool), method, settings).length === 0) {
    return 'Looked up at call start';
  }
  if (Object.keys(settings.bind).length > 0) return 'Details auto-filled';
  if (isReusedInCall(method, settings)) return 'Reused in call';
  return undefined;
};
