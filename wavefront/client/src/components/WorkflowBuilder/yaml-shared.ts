import yaml from 'js-yaml';
import { AgentConfigMethod, AriumAgentConfig, AriumSubworkflowConfig } from '@app/types/workflow-builder';

// Constants and value helpers shared by the YAML parser and serializer

export const TRIGGER_NODE_ID = 'trigger-start';
// flo_ai sentinels: `to: [end]` is skipped by the runtime, `input` in input_filter means the user input
export const END_SENTINEL = 'end';
export const INPUT_SENTINEL = 'input';
export const ROOTFLO_PROVIDER = 'rootflo';
export const MISSING_ARIUM_ERROR = 'The YAML has no top-level `arium` key';

export type Data = Record<string, unknown>;

export const isPlainObject = (value: unknown): value is Data =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

export const hasOwn = (obj: object, key: string) => Object.prototype.hasOwnProperty.call(obj, key);

export const unique = <T>(items: T[]): T[] => Array.from(new Set(items));

// A YAML value that may be one name or a list of names, as a list of names
export const toNameList = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && item !== '')
    : typeof value === 'string' && value
      ? [value]
      : [];

// A string-valued mapping (routing_options, routing_logic, agents), with non-string values read as ''
export const toStringRecord = (value: unknown): Record<string, string> =>
  isPlainObject(value)
    ? Object.fromEntries(Object.entries(value).map(([key, v]) => [key, typeof v === 'string' ? v : '']))
    : {};

// PyYAML (YAML 1.1, what the server uses) also reads yes/no/on/off as booleans; js-yaml (YAML 1.2) keeps them as strings
const YAML11_TRUE = ['true', 'yes', 'on'];
const YAML11_FALSE = ['false', 'no', 'off'];
export const toBool = (value: unknown, fallback: boolean): boolean => {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (YAML11_TRUE.includes(normalized)) return true;
    if (YAML11_FALSE.includes(normalized)) return false;
  }
  return fallback;
};

// A number the user entered, or undefined when the field is blank or not numeric
export const toOptionalNumber = (value: unknown): number | undefined => {
  if (value === '' || value === undefined || value === null) return undefined;
  const n = Number(value);
  return Number.isNaN(n) ? undefined : n;
};

export const setOrDelete = (obj: Data, key: string, value: unknown) => {
  if (value === undefined || value === null || value === '') {
    delete obj[key];
  } else {
    obj[key] = value;
  }
};

// Write a boolean flag without injecting its runtime default into YAML that never set it
export const patchBoolean = (obj: Data, key: string, value: unknown, runtimeDefault: boolean) => {
  if (typeof value !== 'boolean') return;
  if (value === runtimeDefault && !hasOwn(obj, key)) return;
  obj[key] = value;
};

export const describeYamlError = (e: unknown): string => {
  if (e instanceof yaml.YAMLException) {
    return e.mark ? `${e.reason} (line ${e.mark.line + 1})` : e.reason;
  }
  return e instanceof Error ? e.message : String(e);
};

const NODE_LIST_KEYS = ['agents', 'routers', 'function_nodes', 'iterators', 'foreach_nodes', 'ariums'];

// Check that the arium block has the shape the graph is built from, so a malformed document is reported
// instead of being drawn (and saved back) without the parts that could not be read
export const validateAriumShape = (arium: unknown): string | undefined => {
  if (!isPlainObject(arium)) return '`arium` must be a mapping';
  for (const key of NODE_LIST_KEYS) {
    const list = arium[key];
    if (list === undefined || list === null) continue;
    if (!Array.isArray(list)) return `\`arium.${key}\` must be a list`;
    const badIndex = list.findIndex((entry) => !isPlainObject(entry) || typeof entry.name !== 'string' || !entry.name);
    if (badIndex >= 0) return `\`arium.${key}[${badIndex}]\` must be a mapping with a \`name\``;
  }
  const workflow = arium.workflow;
  if (workflow === undefined || workflow === null) return undefined;
  if (!isPlainObject(workflow)) return '`arium.workflow` must be a mapping';
  if (workflow.edges === undefined || workflow.edges === null) return undefined;
  if (!Array.isArray(workflow.edges)) return '`arium.workflow.edges` must be a list';
  const badEdge = workflow.edges.findIndex((edge) => !isPlainObject(edge) || typeof edge.from !== 'string');
  if (badEdge >= 0) return `\`arium.workflow.edges[${badEdge}]\` must be a mapping with a \`from\``;
  return undefined;
};

// Mirrors the server's parse_versioned_reference on the last path segment: 'ns/wf@3' -> 'wf'
export const parseRefLocalName = (ref: string): string => (ref.split('/').pop() || ref).replace(/@.*$/, '');

// Keys that make an `ariums` entry an inline workflow definition (rather than a reference or a yaml_file)
export const INLINE_ARIUM_BODY_KEYS = [
  'agents',
  'function_nodes',
  'routers',
  'ariums',
  'iterators',
  'foreach_nodes',
  'workflow',
];
export const YAML_FILE_PATTERN = /\.ya?ml$/i;

export const hasInlineBody = (entry: Data): boolean => INLINE_ARIUM_BODY_KEYS.some((key) => entry[key] != null);

// A stored-workflow reference: `name: namespace/workflow[@version]` with no body and no yaml_file (server contract)
export const isWorkflowReference = (entry: AriumSubworkflowConfig): boolean =>
  !entry.yaml_file && !hasInlineBody(entry) && entry.name.includes('/');

// The node name an `ariums` entry runs under: the server renames a reference to its local name
export const subworkflowNodeName = (entry: AriumSubworkflowConfig): string =>
  isWorkflowReference(entry) ? parseRefLocalName(entry.name) : entry.name;

export const getAgentConfigMethod = (agent: AriumAgentConfig): AgentConfigMethod => {
  if (agent.yaml_file) return 'yaml_file';
  if (agent.yaml_config) return 'yaml_config';
  if ((agent.job ?? agent.prompt ?? agent.model) != null) return 'inline';
  return 'reference';
};

export const getRouterType = (data: Data): string => (data.strategy as string) || (data.type as string) || 'smart';
