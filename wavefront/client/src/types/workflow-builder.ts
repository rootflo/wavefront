import type { Edge, Node } from '@xyflow/react';

export interface AriumModelConfig {
  provider?: string;
  name?: string;
  // RootFlo LLM inference config id (provider: rootflo)
  model_id?: string;
  [key: string]: unknown;
}

export interface AriumSettingsConfig {
  temperature?: number;
  max_tokens?: number;
  allow_early_exit?: boolean;
  context_description?: string;
  fallback_strategy?: string;
  [key: string]: unknown;
}

// How an `agents` entry is defined: inline (job/prompt + model), a stored-agent reference (name only),
// or an external yaml_file / yaml_config. Stored on agent nodes as data.configMethod.
export type AgentConfigMethod = 'inline' | 'reference' | 'yaml_file' | 'yaml_config';

export interface AriumAgentConfig {
  name: string;
  role?: string;
  job?: string;
  prompt?: string;
  act_as?: string;
  yaml_file?: string;
  yaml_config?: string;
  model?: AriumModelConfig;
  settings?: AriumSettingsConfig;
  // Tool names, or tool config objects (name plus prefilled_params / name_override)
  tools?: Array<string | Record<string, unknown>>;
  input_filter?: string[];
  parser?: unknown;
  [key: string]: unknown;
}

export interface AriumFunctionNodeConfig {
  name: string;
  function_name: string;
  description?: string;
  input_filter?: string[];
  prefilled_params?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface AriumIteratorConfig {
  name: string;
  execute_node?: string;
  input_filter?: string[];
  forward_all_results?: boolean;
  [key: string]: unknown;
}

// Either a stored-workflow reference (`name: namespace/workflow[@version]`), a `yaml_file`, or an inline body
export interface AriumSubworkflowConfig {
  name: string;
  yaml_file?: string;
  inherit_variables?: boolean;
  input_filter?: string[];
  [key: string]: unknown;
}

export interface AriumRouterConfig {
  name: string;
  type?: string;
  strategy?: string;
  model?: AriumModelConfig;
  settings?: AriumSettingsConfig;
  // smart: target -> description
  routing_options?: Record<string, string>;
  // task_classifier: target -> { description, keywords?, examples? }
  task_categories?: Record<string, unknown>;
  // conversation_analysis: target -> routing logic
  routing_logic?: Record<string, string>;
  // reflection: ordered node names
  flow_pattern?: string[] | string;
  // plan_execute: target -> description
  agents?: Record<string, string>;
  // field_match: field value -> target, plus a fallback target
  field?: string;
  routes?: Record<string, string>;
  default?: string;
  [key: string]: unknown;
}

export interface AriumWorkflowEdge {
  from: string;
  to: string | string[];
  router?: string;
}

export interface AriumWorkflowConfig {
  start?: string;
  edges?: AriumWorkflowEdge[];
  end?: string | string[];
  [key: string]: unknown;
}

export interface AriumDoc {
  metadata?: Record<string, unknown>;
  arium?: {
    agents?: AriumAgentConfig[];
    routers?: AriumRouterConfig[];
    function_nodes?: AriumFunctionNodeConfig[];
    iterators?: AriumIteratorConfig[];
    foreach_nodes?: AriumIteratorConfig[];
    ariums?: AriumSubworkflowConfig[];
    workflow?: AriumWorkflowConfig;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

// A problem in the drawn graph that makes the saved workflow fail or run differently from the canvas.
// `nodeId` is set when the problem belongs to one node, so it can be shown on that node.
export interface GraphIssue {
  message: string;
  nodeId?: string;
}

// `error` is set (and the graph is empty) when the YAML cannot be drawn: a syntax error or a document that is not an arium
export interface ParseGraphResult {
  nodes: Node[];
  edges: Edge[];
  error?: string;
}

// `ok: false` means nothing was produced and the current YAML must be kept: `error` says why.
// `ok: true` always carries the YAML; `issues` lists what will fail or misbehave when it runs (empty when none).
export type SerializeGraphResult = { ok: true; yaml: string; issues: GraphIssue[] } | { ok: false; error: string };
