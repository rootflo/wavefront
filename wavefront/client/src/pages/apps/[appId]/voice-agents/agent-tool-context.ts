/**
 * Call context settings for one agent↔tool association: which tool fields
 * (nested ones too, as dotted paths) the server fills in from the call, and whether the tool's answer can be
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
  /** Field path -> server source. Fields not listed are filled by the AI. */
  bind: Record<string, Exclude<ArgumentSource, 'ai'>>;
  readOnly: boolean;
  prefetch: boolean;
}

/** One field the AI (or the server) fills: a top-level argument, or one nested in an object argument. */
export interface ToolArgument {
  /** Dotted path, the key `bind` uses: `mobile_number`, `request.phone`. */
  name: string;
  description?: string;
  /** Required within its own object. */
  required: boolean;
  /** Every call value is text, so only string fields can be filled from the call. */
  bindable: boolean;
  /** Enclosing objects, outermost first, and whether each is required in its parent. */
  parents: { name: string; required: boolean }[];
}

type Overrides = Record<string, unknown> | undefined;

/** Who fills this argument now ('ai' unless the server is set to). */
export const argumentSource = (settings: Pick<ToolContextSettings, 'bind'>, arg: string): ArgumentSource =>
  settings.bind[arg] ?? 'ai';

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};

/** The tool's fields from its JSON-schema `parameter_schema`, with objects opened up to their fields. */
export const toolArguments = (tool: Pick<VoiceAgentTool, 'parameter_schema'>): ToolArgument[] => {
  const fields: ToolArgument[] = [];
  const walk = (node: Record<string, unknown>, prefix: string, parents: ToolArgument['parents']) => {
    const required = new Set(Array.isArray(node.required) ? node.required.map(String) : []);
    Object.entries(asRecord(node.properties)).forEach(([key, value]) => {
      const spec = asRecord(value);
      const name = `${prefix}${key}`;
      if (Object.keys(asRecord(spec.properties)).length > 0) {
        walk(spec, `${name}.`, [...parents, { name, required: required.has(key) }]);
        return;
      }
      fields.push({
        name,
        description: typeof spec.description === 'string' ? spec.description : undefined,
        required: required.has(key),
        bindable: spec.type === 'string',
        parents,
      });
    });
  };
  walk(asRecord(tool.parameter_schema), '', []);
  return fields;
};

/** How a field path reads in the UI: `request › phone`. */
export const fieldLabel = (name: string) => name.split('.').join(' › ');

/**
 * The saved binds that apply on a call, and the ones the server ignores (no such
 * text field, e.g. an object argument bound as a whole). Saving drops the ignored.
 */
export const usableBind = (
  args: ToolArgument[],
  bind: ToolContextSettings['bind']
): { bind: ToolContextSettings['bind']; ignored: string[] } => {
  const bindable = new Set(args.filter((a) => a.bindable).map((a) => a.name));
  const usable: ToolContextSettings['bind'] = {};
  const ignored: string[] = [];
  Object.entries(bind).forEach(([name, source]) => {
    if (bindable.has(name)) usable[name] = source;
    else ignored.push(name);
  });
  return { bind: usable, ignored };
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
  const bound = Object.keys(settings.bind);
  // An object is sent when it is required or holds a filled field; optional fields left to the AI are just left out
  const isSent = (parent: { name: string; required: boolean }) =>
    parent.required || bound.some((name) => name.startsWith(`${parent.name}.`));
  const leftToAi = args
    .filter((a) => a.required && !settings.bind[a.name] && a.parents.every(isSent))
    .map((a) => fieldLabel(a.name));
  if (leftToAi.length > 0) {
    blockers.push(
      `Before the call starts nobody has spoken yet, so every required detail must be filled automatically. ` +
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

/** A likely server source for a text field, from its own name. */
export const suggestedSource = (arg: ToolArgument): Exclude<ArgumentSource, 'ai'> | undefined => {
  if (!arg.bindable) return undefined;
  const ownName = arg.name.split('.').pop() ?? arg.name;
  if (PHONE_NAME.test(ownName)) return 'caller.phone';
  if (CALL_ID_NAME.test(ownName)) return 'call.id';
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
      `The server sends ${SOURCE_PHRASES[source]} as "${fieldLabel(arg)}". ` +
      `The AI doesn't see this detail and won't ask for it.`
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
  const args = toolArguments(tool);
  const saved = readToolContext(overrides);
  const settings = { ...saved, bind: usableBind(args, saved.bind).bind };
  const method = effectiveMethod(tool, overrides);
  if (settings.prefetch && prefetchBlockers(args, method, settings).length === 0) {
    return 'Looked up at call start';
  }
  if (Object.keys(settings.bind).length > 0) return 'Details auto-filled';
  if (isReusedInCall(method, settings)) return 'Reused in call';
  return undefined;
};
