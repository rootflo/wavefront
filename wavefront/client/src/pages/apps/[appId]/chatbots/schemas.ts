import { z } from 'zod';

/** Mirrors the backend's validate_agent_workflow_name pattern. */
export const CHATBOT_NAME_PATTERN = /^[a-zA-Z][a-zA-Z0-9_-]*$/;

export const TEMPERATURE_MIN = 0;
export const TEMPERATURE_MAX = 2;

/**
 * Temperature is held as a STRING in the form, deliberately.
 *
 * `z.coerce.number()` turns '' into 0, and 0 is a real setting -- fully
 * deterministic output -- so every chatbot whose author never touched the field
 * would be silently pinned to temperature 0. Keeping it a string makes "unset"
 * and "zero" distinguishable, which is the same distinction the backend makes
 * by testing key presence rather than truthiness.
 */
const temperatureSchema = z.string().refine(
  (value) => {
    const raw = value.trim();
    if (raw === '') return true; // unset -> use the model's own setting
    const parsed = Number(raw);
    return Number.isFinite(parsed) && parsed >= TEMPERATURE_MIN && parsed <= TEMPERATURE_MAX;
  },
  { message: `Temperature must be a number between ${TEMPERATURE_MIN} and ${TEMPERATURE_MAX}, or left blank` }
);

/**
 * What answers for the chatbot: a prompt sent straight to a model, or an agent
 * (which brings its own prompt, model and tools).
 */
export const CHAT_TYPE_LLM = 'llm';
export const CHAT_TYPE_AGENT = 'agent';

/**
 * Held as a string for the same reason temperature is: blank means "follow the
 * agent's current version", which a coerced number could not tell from 0.
 */
const agentVersionSchema = z.string().refine(
  (value) => {
    const raw = value.trim();
    if (raw === '') return true;
    const parsed = Number(raw);
    return Number.isInteger(parsed) && parsed >= 1;
  },
  { message: 'Version must be a whole number of 1 or more, or left blank' }
);

export const chatbotFormSchema = z
  .object({
    chat_type: z.enum([CHAT_TYPE_LLM, CHAT_TYPE_AGENT]),
    name: z
      .string()
      .min(1, 'Name is required')
      .max(255, 'Name must be 255 characters or fewer')
      .regex(
        CHATBOT_NAME_PATTERN,
        'Name must start with a letter and contain only letters, digits, underscores and hyphens'
      ),
    namespace: z.string().min(1, 'Namespace is required'),
    description: z.string().max(500, 'Description must be 500 characters or fewer'),
    // Which of the next four are required depends on chat_type: see below.
    system_prompt: z.string(),
    llm_config_id: z.string(),
    agent_id: z.string(),
    agent_version: agentVersionSchema,
    welcome_message: z.string(),
    temperature: temperatureSchema,
    enabled: z.boolean(),
  })
  .superRefine((values, ctx) => {
    if (values.chat_type === CHAT_TYPE_AGENT) {
      if (!values.agent_id) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['agent_id'], message: 'Agent is required' });
      }
      return;
    }
    if (!values.system_prompt.trim()) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['system_prompt'], message: 'System prompt is required' });
    }
    if (!values.llm_config_id) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['llm_config_id'],
        message: 'LLM configuration is required',
      });
    }
  });

export type ChatbotFormValues = z.infer<typeof chatbotFormSchema>;

/** Form string -> the `config` object the API expects. `{}` means no override. */
export const buildConfig = (temperature: string): Record<string, unknown> => {
  const raw = temperature.trim();
  return raw === '' ? {} : { temperature: Number(raw) };
};

/**
 * `config` -> form string. Tests key presence so a stored 0 round-trips as '0'
 * rather than being mistaken for "unset".
 */
export const readTemperature = (config: Record<string, unknown> | null | undefined): string => {
  if (config && 'temperature' in config && config.temperature !== null) {
    return String(config.temperature);
  }
  return '';
};

/** Form string -> the pinned version, or `undefined` to follow the agent's current one. */
export const parseAgentVersion = (version: string): number | undefined => {
  const raw = version.trim();
  return raw === '' ? undefined : Number(raw);
};

/** Display helper for the list column. */
export const formatTemperature = (config: Record<string, unknown> | null | undefined): string => {
  const value = readTemperature(config);
  return value === '' ? '—' : value;
};
