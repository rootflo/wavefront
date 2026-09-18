import { FailureMode, PiiEntityGroup, WorkflowStage } from '@app/api/guardrails-service';

export interface AdapterMeta {
  title: string;
  description: string;
  /** Shown when the server has the check but cannot run it. */
  unavailableHint: string;
  defaultStages: WorkflowStage[];
  defaultOnError: FailureMode;
  defaultOptions: Record<string, unknown>;
}

/**
 * Presentation and sensible defaults for each safety check.
 *
 * Titles and copy here deliberately describe what a check does rather than
 * which engine implements it. The vendor behind a check is a deployment
 * concern that can change without the policy changing, so it stays out of the
 * console; the adapter keys below are the only place it appears.
 *
 * Kept out of the component file so fast refresh keeps working — a module that
 * exports both components and constants is reloaded wholesale on edit.
 */
export const ADAPTER_META: Record<string, AdapterMeta> = {
  presidio_pii: {
    title: 'PII detection and redaction',
    description:
      'Detects personal identifiers and replaces them before the text is sent onward. Choose exactly which types to redact below. Runs inside your own deployment, so it keeps working when external services are unavailable.',
    unavailableHint:
      'This check is missing a server-side dependency. Install it and restart the server to make it selectable here.',
    defaultStages: ['BEFORE_MODEL', 'AFTER_MODEL'],
    // Redaction failing means PII may already be on its way to a third party
    // or back to a user, and neither can be undone.
    defaultOnError: 'FAIL_CLOSED',
    defaultOptions: {},
  },
  azure_content_safety: {
    title: 'Content safety policy',
    description:
      'Moderates hate, self-harm, sexual and violent content by severity, and detects prompt injection and jailbreak attempts.',
    unavailableHint:
      'This check calls an external moderation service that is not configured on this server. Once its credentials are set and the server restarts, it becomes selectable here.',
    defaultStages: ['BEFORE_MODEL'],
    // A remote outage should not take inference down; a toxic prompt reaching
    // your own model is bounded and reversible.
    defaultOnError: 'FAIL_OPEN',
    defaultOptions: { severity_threshold: 4, enable_prompt_shields: true },
  },
};

/** Fallback hint for a check this build has no metadata for. */
export const DEFAULT_UNAVAILABLE_HINT =
  'This check is not available on this server. Check its configuration and restart the server to make it selectable here.';

/**
 * Display name for an adapter key.
 *
 * Adapter keys are how the API names each check, and they carry the vendor
 * with them (`presidio_pii`, `azure_content_safety`). Anything rendered from
 * an API value therefore goes through here rather than being printed raw.
 *
 * An unknown key falls back to itself: a check this build has never heard of
 * is one an operator has to go and look up, and the key is the only handle
 * they have on it.
 */
export const adapterLabel = (name: string | null | undefined): string => {
  if (!name) return 'Unknown check';
  return ADAPTER_META[name]?.title ?? name;
};

/**
 * Entity id to the label the selector shows for it, e.g. `IN_AADHAAR` to
 * "Aadhaar number".
 *
 * Verdicts name entities by id, because that is what the detection engine and
 * the stored policy both speak. The selector has only ever shown labels, so a
 * result reading `IN_AADHAAR, US_SSN` asks the reader to hold two vocabularies
 * for one list of identifiers.
 *
 * Ids missing from the catalog keep their id. The catalog is fetched
 * separately and describes what this build knows about, so a deployment whose
 * recognisers are ahead of it can return an id with no entry — showing that id
 * is the only honest thing left to do.
 */
export const buildEntityLabels = (groups: PiiEntityGroup[] | undefined): Map<string, string> =>
  new Map((groups ?? []).flatMap((group) => group.entities.map((entity) => [entity.id, entity.label] as const)));

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
