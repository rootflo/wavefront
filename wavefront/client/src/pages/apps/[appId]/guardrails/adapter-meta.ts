import { FailureMode, WorkflowStage } from '@app/api/guardrails-service';

export interface AdapterMeta {
  title: string;
  description: string;
  defaultStages: WorkflowStage[];
  defaultOnError: FailureMode;
  defaultOptions: Record<string, unknown>;
}

/**
 * Presentation and sensible defaults for each safety provider.
 *
 * Kept out of the component file so fast refresh keeps working — a module that
 * exports both components and constants is reloaded wholesale on edit.
 */
export const ADAPTER_META: Record<string, AdapterMeta> = {
  presidio_pii: {
    title: 'PII detection and redaction',
    description:
      'Detects personal identifiers and replaces them before the text is sent onward. Choose exactly which types to redact below. Runs locally, so it keeps working when a remote provider is unavailable.',
    defaultStages: ['BEFORE_MODEL', 'AFTER_MODEL'],
    // Redaction failing means PII may already be on its way to a third party
    // or back to a user, and neither can be undone.
    defaultOnError: 'FAIL_CLOSED',
    defaultOptions: {},
  },
  azure_content_safety: {
    title: 'Azure Content Safety',
    description:
      'Category moderation for hate, self-harm, sexual and violent content, plus Prompt Shields for injection and jailbreak attempts.',
    defaultStages: ['BEFORE_MODEL'],
    // A remote outage should not take inference down; a toxic prompt reaching
    // your own model is bounded and reversible.
    defaultOnError: 'FAIL_OPEN',
    defaultOptions: { severity_threshold: 4, enable_prompt_shields: true },
  },
};

export const STAGE_LABELS: Record<WorkflowStage, string> = {
  BEFORE_MODEL: 'Check prompts (input)',
  AFTER_MODEL: 'Check responses (output)',
};

/**
 * Warning shown against entity types that match loosely.
 *
 * `validated` entities run a checksum or a dedicated library and only fire on
 * real identifiers, so they need no caveat. The other two do: a `pattern`
 * entity is a bare regex — German postcodes are any five-digit number — and an
 * `nlp` entity is inferred from prose, so it fires on ordinary sentences.
 */
export const PRECISION_WARNINGS: Record<string, string | null> = {
  validated: null,
  pattern: 'Matches on shape alone',
  nlp: 'Inferred from context',
};

/** Below this, a pattern-only entity is loose enough to warrant a warning. */
export const LOOSE_PATTERN_SCORE = 0.3;

export const PRECISION_TOOLTIPS: Record<string, string> = {
  validated: 'Verified with a checksum, so false positives are rare.',
  pattern: 'Recognised by shape only, with no checksum to confirm it. Expect some ordinary numbers to be redacted.',
  nlp: 'Identified by a language model from surrounding context. Fires on ordinary prose, so review before enforcing.',
};

export const SEVERITY_LABELS: Record<number, string> = {
  0: 'Everything (severity 0+)',
  2: 'Low and above',
  4: 'Medium and above',
  6: 'High only',
};
