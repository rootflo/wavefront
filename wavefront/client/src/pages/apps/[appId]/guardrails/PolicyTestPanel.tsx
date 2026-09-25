import floConsoleService from '@app/api';
import {
  EnforcementMode,
  GuardrailAdapterConfig,
  PiiEntityGroup,
  PolicyPreviewStage,
  PolicyPreviewResult,
} from '@app/api/guardrails-service';
import { Button } from '@app/components/ui/button';
import { Label } from '@app/components/ui/label';
import { Textarea } from '@app/components/ui/textarea';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import React, { forwardRef, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { adapterLabel, buildEntityLabels } from './adapter-meta';

export interface PolicyTestHandle {
  /** Scroll the panel into view and put the cursor in the textarea. */
  focus: () => void;
}

interface Props {
  isEnabled: boolean;
  mode: EnforcementMode;
  adapters: GuardrailAdapterConfig[];
  /** Entity catalog, used to name detections the way the selector does. */
  piiGroups?: PiiEntityGroup[];
}

const ACTION_STYLES: Record<string, string> = {
  ALLOW: 'bg-green-100 text-green-800',
  TRANSFORM: 'bg-amber-100 text-amber-800',
  BLOCK: 'bg-red-100 text-red-800',
};

const STAGE_LABELS: Record<string, string> = {
  BEFORE_MODEL: 'Prompt (input)',
  AFTER_MODEL: 'Response (output)',
};

const ActionBadge: React.FC<{ action: string }> = ({ action }) => (
  <span className={`rounded px-2 py-0.5 text-xs font-medium ${ACTION_STYLES[action] ?? 'bg-gray-100 text-gray-700'}`}>
    {action}
  </span>
);

/**
 * Restate a PII verdict using the names from the selector.
 *
 * The check's own message lists entity ids — "Redacted 4 PII entities:
 * CREDIT_CARD, IN_AADHAAR, ..." — which is the vocabulary of the detection
 * engine, not of the page the reader just ticked boxes on. The same verdict
 * carries `entity_counts` in its metadata, so the list can be rebuilt here in
 * the selector's words instead.
 *
 * Returns null for anything without that metadata, which is every other check;
 * those keep their own message verbatim.
 */
const piiSummary = (result: PolicyPreviewResult, labels: Map<string, string>): string | null => {
  const counts = result.metadata?.entity_counts;
  if (!counts || typeof counts !== 'object') return null;

  const entries = Object.entries(counts as Record<string, unknown>);
  if (entries.length === 0) return null;

  const total = entries.reduce((sum, [, count]) => sum + (Number(count) || 0), 0);
  // By label, not by id: sorting on ids would order the list by words the
  // reader cannot see.
  const names = entries.map(([id]) => labels.get(id) ?? id).sort((a, b) => a.localeCompare(b));
  return `Redacted ${total} ${total === 1 ? 'identifier' : 'identifiers'}: ${names.join(', ')}`;
};

const ResultRow: React.FC<{ result: PolicyPreviewResult; labels: Map<string, string> }> = ({ result, labels }) => {
  const message = piiSummary(result, labels) ?? result.message;

  return (
    <div className="flex items-start justify-between gap-4 border-t border-gray-100 py-2 text-sm">
      <div>
        {/* The API answers with adapter keys; those name the engine, so they are labelled before display. */}
        <span className="font-medium text-gray-800">{adapterLabel(result.adapter)}</span>
        {message && <p className="mt-0.5 text-gray-600">{message}</p>}
        {result.failure_class !== 'NONE' && (
          <p className="mt-0.5 text-xs text-red-700">failure: {result.failure_class}</p>
        )}
      </div>
      <ActionBadge action={result.action} />
    </div>
  );
};

const StageResult: React.FC<{ stage: PolicyPreviewStage; labels: Map<string, string> }> = ({ stage, labels }) => {
  // In monitor mode `action` is always ALLOW, so showing it alone would make
  // every policy look inert. The verdict is what the admin is testing.
  const verdict = stage.enforced ? stage.action : stage.observed_action;

  return (
    <div className="rounded-lg border border-gray-200 p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-900">{STAGE_LABELS[stage.stage] ?? stage.stage}</span>
        <div className="flex items-center gap-2">
          {!stage.enforced && verdict !== 'ALLOW' && (
            <span className="text-xs text-gray-500">would have — monitor mode applies nothing</span>
          )}
          <ActionBadge action={verdict} />
        </div>
      </div>

      {stage.results.length === 0 ? (
        <p className="mt-2 text-sm text-gray-500">No checks run at this stage.</p>
      ) : (
        <div className="mt-2">
          {stage.results.map((result, i) => (
            <ResultRow key={`${result.adapter}-${i}`} result={result} labels={labels} />
          ))}
        </div>
      )}

      {stage.transformed_text && (
        <div className="mt-3">
          <Label className="text-xs text-gray-500">Text after redaction</Label>
          <pre className="mt-1 overflow-x-auto rounded bg-gray-50 p-2 text-sm whitespace-pre-wrap text-gray-800">
            {stage.transformed_text}
          </pre>
        </div>
      )}
    </div>
  );
};

/**
 * Runs the unsaved policy through the real engine against sample text.
 *
 * Deliberately behind an explicit button rather than firing as you type: the
 * content safety check calls a metered external service (Azure Content Safety)
 * that bills per call and rate-limits, so a debounced preview would quietly
 * cost money on every keystroke.
 */
const PolicyTestPanel = forwardRef<PolicyTestHandle, Props>(({ isEnabled, mode, adapters, piiGroups }, ref) => {
  const { notifyError } = useNotifyStore();
  const [text, setText] = useState('');
  const [running, setRunning] = useState(false);
  const [stages, setStages] = useState<PolicyPreviewStage[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Scrolling and focusing live here rather than in the page, because the
  // panel owns the textarea. Focus as well as scroll: the point of the header
  // button is to start typing a test, and landing near the box without the
  // cursor in it means a second click every time.
  useImperativeHandle(ref, () => ({
    focus: () => {
      panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      textareaRef.current?.focus({ preventScroll: true });
    },
  }));

  const entityLabels = useMemo(() => buildEntityLabels(piiGroups), [piiGroups]);

  // Only warn when a run would actually bill. PII redaction is in-process and
  // free, so a cost notice on a PII-only policy trains people to ignore it.
  const contentSafety = adapters.find((adapter) => adapter.name === 'azure_content_safety');
  const contentSafetyStages = contentSafety?.stages.length ?? 0;
  const injectionCheckOn =
    !!contentSafety &&
    contentSafety.options?.enable_prompt_shields !== false &&
    contentSafety.stages.includes('BEFORE_MODEL');
  const billable = isEnabled && contentSafetyStages > 0;

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    try {
      const response = await floConsoleService.guardrailsService.previewPolicy({
        text,
        is_enabled: isEnabled,
        mode,
        adapters,
      });
      // Envelope is { meta, data }, so the payload is one level below
      // response.data. Reading response.data.stages yields undefined and
      // renders nothing at all, which looks like the button doing nothing.
      if (response.data?.meta?.status === 'success' && response.data.data?.stages) {
        setStages(response.data.data.stages);
      } else {
        setStages(null);
        setError('The server did not return a result.');
      }
    } catch (err) {
      setStages(null);
      setError(extractErrorMessage(err));
      notifyError(extractErrorMessage(err));
    } finally {
      setRunning(false);
      // Only below lg, where the two columns stack and the results land off
      // screen. On wide screens they are already beside the button, and
      // scrolling there would move the page for no reason.
      if (window.matchMedia('(max-width: 1023px)').matches) {
        resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  };

  return (
    <div ref={panelRef} className="scroll-mt-4">
      <h2 className="mb-1 text-lg font-semibold text-gray-900">Test this policy</h2>
      <p className="mb-4 text-sm text-gray-600">
        Runs the settings above — saved or not — through the real engine. Nothing is stored.
      </p>

      {/*
        Side by side once there is room, rather than results below the button.
        A test tool is used iteratively: you read the verdict, edit the text and
        run again, so the input has to stay on screen next to its result. The
        input column is sticky because results grow much taller than it does.
      */}
      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-2">
        <div className="lg:sticky lg:top-4">
          <Textarea
            ref={textareaRef}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Paste sample text, e.g. a prompt containing a card number"
            rows={6}
            maxLength={4000}
          />

          {billable && (
            <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-3">
              <p className="text-sm font-medium text-amber-900">Content safety policy is on — test runs are billed</p>
              <p className="mt-1 text-sm text-amber-800">
                Each run sends this text to an external moderation service once for every stage it checks (
                {contentSafetyStages}
                {contentSafetyStages === 1 ? ' stage' : ' stages'})
                {injectionCheckOn ? ', and prompt injection detection is a further call on the prompt' : ''}. Text over
                10,000 characters is split into chunks that are billed separately. PII redaction runs inside your
                deployment and costs nothing. Nothing is sent until you press Run test.
              </p>
            </div>
          )}

          <div className="mt-3 flex items-center gap-3">
            <Button onClick={handleRun} disabled={running || !text.trim()}>
              {running ? 'Running...' : 'Run test'}
            </Button>
            {!isEnabled && <span className="text-sm text-gray-500">Guardrails are off, so nothing will run.</span>}
          </div>
        </div>

        <div ref={resultsRef} className="scroll-mt-4">
          {error && <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800">{error}</div>}

          {!error && stages === null && (
            <div className="rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">
              Run a test to see what each check does to your text, at both stages.
            </div>
          )}

          {!error && stages?.length === 0 && (
            <div className="rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">
              No checks ran. Nothing is configured for either stage.
            </div>
          )}

          {!error && stages && stages.length > 0 && (
            <div className="flex flex-col gap-3">
              {stages.map((stage) => (
                <StageResult key={stage.stage} stage={stage} labels={entityLabels} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

PolicyTestPanel.displayName = 'PolicyTestPanel';

export default PolicyTestPanel;
