export interface LLMConfig {
  provider: 'openai' | 'anthropic' | 'gemini' | 'ollama';
  name: string;
  base_url?: string;
}

export interface AgentSettings {
  temperature?: number;
  max_retries?: number;
  reasoning_pattern?: 'DIRECT' | 'REACT' | 'COT';
}

export interface ParserField {
  name: string;
  type: 'str' | 'literal' | 'array' | 'object';
  description?: string;
  required?: boolean;
  values?: Array<{
    value: string;
    description: string;
    examples?: string[];
  }>;
  items?: {
    type: string;
  };
}

export interface Parser {
  name: string;
  version?: string;
  description?: string;
  fields: ParserField[];
}

export interface Agent {
  id: string;
  name: string;
  role?: string;
  job: string;
  model: LLMConfig;
  settings?: AgentSettings;
  tools?: string[];
  parser?: Parser;
  position?: { x: number; y: number };
}

export interface Tool {
  name: string;
  description: string;
  parameters?: Record<string, any>;
}

export interface Router {
  id?: string;
  name: string;
  description: string;
  type?: 'smart' | 'task_classifier' | 'conversation_analysis' | 'reflection' | 'plan_execute' | 'custom';
  code?: string;
  routing_options?: Record<string, string>;
  model?: LLMConfig;
  settings?: {
    temperature?: number;
    fallback_strategy?: 'first' | 'last' | 'random';
    analysis_depth?: number;
    allow_early_exit?: boolean;
  };
  task_categories?: Record<string, {
    description: string;
    keywords: string[];
    examples: string[];
  }>;
  routing_logic?: Record<string, string>;
  flow_pattern?: string[];
}

export interface WorkflowEdge {
  id: string;
  from: string;
  to: string[];
  router?: string;
}

export interface AriumWorkflow {
  metadata: {
    name: string;
    version?: string;
    description?: string;
    tags?: string[];
  };
  arium: {
    agents: Agent[];
    tools?: Tool[];
    workflow: {
      start: string;
      edges: Array<{
        from: string;
        to: string[];
        router?: string;
      }>;
      end: string[];
    };
  };
}

export interface DesignerConfig {
  availableTools: Tool[];
  availableLLMs: LLMConfig[];
  availableRouters: Router[];
}
