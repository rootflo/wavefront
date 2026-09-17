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

export const chatbotFormSchema = z.object({
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
  system_prompt: z.string().min(1, 'System prompt is required'),
  welcome_message: z.string(),
  llm_config_id: z.string().min(1, 'LLM configuration is required'),
  temperature: temperatureSchema,
  enabled: z.boolean(),
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

/** Display helper for the list column. */
export const formatTemperature = (config: Record<string, unknown> | null | undefined): string => {
  const value = readTemperature(config);
  return value === '' ? '—' : value;
};
