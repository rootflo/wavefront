import { z } from 'zod';
import { AGENT_ID_PATTERN, AGENT_ID_PATTERN_MESSAGE, TEMPERATURE_RANGE } from '@app/constants/workflow-builder';
import { validateAgentYaml } from './agentYamlMapper';

export { AGENT_ID_PATTERN, TEMPERATURE_RANGE };

export const REASONING_PATTERNS = [
  { value: 'DIRECT', label: 'Direct' },
  { value: 'REACT', label: 'ReAct' },
  { value: 'COT', label: 'Chain of Thought (COT)' },
] as const;

export const ACT_AS_OPTIONS = [
  { value: 'assistant', label: 'Assistant' },
  { value: 'user', label: 'User' },
  { value: 'system', label: 'System' },
] as const;

// Bounds mirror flo_ai's SettingsModel, so the form rejects what the server would reject.
const penalty = z.number().min(-2, 'Must be between -2 and 2').max(2, 'Must be between -2 and 2').nullable().optional();
const positiveInt = z.number().int('Must be a whole number').positive('Must be greater than 0').nullable().optional();

/**
 * Fields shared by the Create and Edit agent dialogs. Every field except yamlContent maps onto a key
 * of the agent YAML (see agentYamlMapper.ts); YAML-only settings (max_retries, provider-specific model
 * keys, parser, examples, ...) are deliberately not part of the form so they are never rewritten.
 */
export const agentFormSchema = z.object({
  yamlContent: z.string().min(1, 'YAML configuration is required'),

  // Identity & Metadata
  agentName: z.string().optional(),
  role: z.string().optional(),
  job: z.string().refine((value) => value.trim().length > 0, 'System prompt is required'),
  description: z.string().optional(),
  tags: z.string().optional(), // Comma separated for simplicity in form
  actAs: z.string().optional(),

  // Model Config (RootFlo LLM config id; other providers are edited in YAML)
  modelId: z.string().optional(),

  // Settings
  temperature: z.number().min(TEMPERATURE_RANGE.min).max(TEMPERATURE_RANGE.max).nullable().optional(),
  maxTokens: positiveInt,
  reasoningPattern: z.string().optional(),
  topP: z.number().min(0, 'Must be between 0 and 1').max(1, 'Must be between 0 and 1').nullable().optional(),
  topK: positiveInt,
  frequencyPenalty: penalty,
  presencePenalty: penalty,
  seed: z.number().int('Must be a whole number').nullable().optional(),
});

export type AgentFormValues = z.infer<typeof agentFormSchema>;

// Checks the YAML that is actually submitted (model provider requirements, agent.name), so a save from
// either tab fails inline instead of with a generic server error.
const refineAgentYaml = (values: { yamlContent: string }, ctx: z.RefinementCtx) => {
  for (const issue of validateAgentYaml(values.yamlContent)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: [issue.field], message: issue.message });
  }
};

export const createAgentSchema = agentFormSchema
  .extend({
    agentId: z.string().trim().min(1, 'Agent name is required').regex(AGENT_ID_PATTERN, AGENT_ID_PATTERN_MESSAGE),
    namespace: z.string().min(1, 'Namespace is required'),
  })
  .superRefine(refineAgentYaml);

export type CreateAgentInput = z.infer<typeof createAgentSchema>;

export const editAgentSchema = agentFormSchema
  .extend({
    agentName: z.string().refine((value) => value.trim().length > 0, 'Agent name is required'),
    selectedTools: z.array(z.object({ id: z.string(), value: z.string() })).optional(),
  })
  .superRefine(refineAgentYaml);

export type EditAgentInput = z.infer<typeof editAgentSchema>;

/** Human-readable labels used when a validation error has to be reported outside its field. */
export const AGENT_FIELD_LABELS: Record<string, string> = {
  yamlContent: 'YAML',
  agentId: 'Agent name',
  namespace: 'Namespace',
  agentName: 'Agent name',
  role: 'Role',
  job: 'System prompt',
  description: 'Description',
  tags: 'Tags',
  actAs: 'Act as',
  modelId: 'LLM model',
  temperature: 'Temperature',
  maxTokens: 'Max tokens',
  reasoningPattern: 'Reasoning pattern',
  topP: 'Top P',
  topK: 'Top K',
  frequencyPenalty: 'Frequency penalty',
  presencePenalty: 'Presence penalty',
  seed: 'Seed',
};
