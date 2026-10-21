export interface AriumModelConfig {
  provider?: string;
  name?: string;
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

export interface AriumAgentConfig {
  name: string;
  role?: string;
  job?: string;
  prompt?: string;
  act_as?: string;
  yaml_file?: string;
  model?: AriumModelConfig;
  settings?: AriumSettingsConfig;
  tools?: string[];
  input_filter?: string[];
  parser?: unknown;
  [key: string]: unknown;
}

export interface AriumFunctionNodeConfig {
  name: string;
  function_name: string;
  description?: string;
  input_filter?: string[];
  prefilled_params?: unknown;
  [key: string]: unknown;
}

export interface AriumIteratorConfig {
  name: string;
  execute_node?: string;
  input_filter?: string[];
  forward_all_results?: boolean;
  [key: string]: unknown;
}

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
  field?: string;
  flow_pattern?: string[] | string;
  routing_options?: Record<string, string>;
  routes?: Record<string, string>;
  model?: AriumModelConfig;
  settings?: AriumSettingsConfig;
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
