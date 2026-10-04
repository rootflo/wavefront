import floConsoleService from '@app/api';
import { PiiEntityGroup, PiiPreviewResult } from '@app/api/guardrails-service';
import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Label } from '@app/components/ui/label';
import { Textarea } from '@app/components/ui/textarea';
import { extractErrorMessage } from '@app/lib/utils';
import React, { useEffect, useMemo, useState } from 'react';
import { buildEntityLabels } from './adapter-meta';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The draft options being edited, sent as-is so preview matches the policy. */
  options: Record<string, unknown>;
  /** Entity catalog, used to name detections the way the selector does. */
  groups?: PiiEntityGroup[];
}

const MAX_CHARS = 4000;

const SAMPLE =
  'Hi, this is Priya. My Aadhaar is 2341 2341 2346 and my card is 4111 1111 1111 1111.\n' +
  'Reach me at priya@example.com or +91 98765 43210. Order #234567890 shipped Monday.';

/**
 * Collapse findings that cover the same or overlapping text.
 *
 * Several recognisers routinely claim one span: a nine-digit order number
 * matches US_BANK_NUMBER, US_PASSPORT and US_SSN at once, because all three
 * are shape-only patterns. Those arrive as separate findings, so rendering one
 * highlight per finding repeats the same characters once per match. Presidio
 * merges them before anonymising, which is why the redacted output is correct
 * while the highlighted view was not.
 */
const mergeSpans = (findings: PiiPreviewResult['findings']) => {
  const sorted = [...findings].sort((a, b) => a.start - b.start || a.end - b.end);
  const merged: Array<{ start: number; end: number; entities: string[] }> = [];

  for (const finding of sorted) {
    const last = merged[merged.length - 1];
    // Strictly less than, so a match starting exactly where the previous one
    // ends stays a separate highlight rather than being absorbed.
    if (last && finding.start < last.end) {
      last.end = Math.max(last.end, finding.end);
      if (!last.entities.includes(finding.entity_type)) last.entities.push(finding.entity_type);
    } else {
      merged.push({ start: finding.start, end: finding.end, entities: [finding.entity_type] });
    }
  }
  return merged;
};

/** Split text into redacted/untouched runs so matches can be highlighted. */
const segments = (text: string, findings: PiiPreviewResult['findings']) => {
  const parts: Array<{ text: string; entities: string[] | null }> = [];
  let cursor = 0;
  for (const span of mergeSpans(findings)) {
    if (span.start > cursor) parts.push({ text: text.slice(cursor, span.start), entities: null });
    parts.push({ text: text.slice(span.start, span.end), entities: span.entities });
    cursor = span.end;
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor), entities: null });
  return parts;
};

const PiiPreviewDialog: React.FC<Props> = ({ open, onOpenChange, options, groups }) => {
  const labels = useMemo(() => buildEntityLabels(groups), [groups]);
  const [text, setText] = useState(SAMPLE);
  const [result, setResult] = useState<PiiPreviewResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  // Discard the previous run whenever the dialog is reopened. The selection it
  // was produced under has usually changed by then, and a result that no longer
  // reflects the settings on screen is worse than no result at all.
  useEffect(() => {
    if (open) {
      setResult(null);
      setError(null);
    }
  }, [open]);

  const run = async () => {
    setRunning(true);
    setError(null);
    // Clear before awaiting, so a slow run never shows the old output next to
    // freshly edited sample text.
    setResult(null);
    try {
      const response = await floConsoleService.guardrailsService.previewPii({ text, options });
      if (response.data?.meta?.status === 'success' && response.data.data?.result) {
        setResult(response.data.data.result);
      } else {
        setError('The server did not return a result.');
      }
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setRunning(false);
    }
  };

  const counts = result
    ? result.findings.reduce<Record<string, number>>((acc, finding) => {
        acc[finding.entity_type] = (acc[finding.entity_type] ?? 0) + 1;
        return acc;
      }, {})
    : {};

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Test this policy</DialogTitle>
          <DialogDescription>
            Runs the settings currently on screen against your sample text. Nothing is saved and the stored policy is
            not changed.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div>
            <div className="flex items-center justify-between">
              <Label className="text-sm font-medium">Sample text</Label>
              <span className={`text-xs ${text.length > MAX_CHARS ? 'text-red-600' : 'text-gray-400'}`}>
                {text.length} / {MAX_CHARS}
              </span>
            </div>
            <Textarea
              className="mt-2 h-32 font-mono text-xs"
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
          </div>

          {error && <p className="rounded-md border border-red-300 bg-red-50 p-3 text-xs text-red-800">{error}</p>}

          {result && (
            <div className="flex flex-col gap-3">
              <div>
                <Label className="text-xs font-medium text-gray-500">Detected</Label>
                <div className="mt-1.5 rounded-md border border-gray-200 p-3 text-xs leading-relaxed whitespace-pre-wrap">
                  {result.findings.length === 0 ? (
                    <span className="text-gray-500">
                      Nothing was detected. Either this text contains none of the selected types, or the identifiers in
                      it failed their checksum.
                    </span>
                  ) : (
                    segments(text, result.findings).map((part, index) =>
                      part.entities ? (
                        <mark
                          key={index}
                          title={part.entities.map((entity) => labels.get(entity) ?? entity).join(', ')}
                          className="rounded bg-amber-200 px-0.5"
                        >
                          {part.text}
                        </mark>
                      ) : (
                        <span key={index}>{part.text}</span>
                      )
                    )
                  )}
                </div>
              </div>

              <div>
                <Label className="text-xs font-medium text-gray-500">What the model would receive</Label>
                <div className="mt-1.5 rounded-md border border-gray-200 bg-gray-50 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap">
                  {result.redacted_text}
                </div>
              </div>

              {result.findings.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(counts).map(([entity, count]) => (
                    <span key={entity} className="rounded bg-gray-100 px-2 py-0.5 text-[11px] text-gray-700">
                      {labels.get(entity) ?? entity} × {count}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button onClick={run} disabled={running || !text.trim() || text.length > MAX_CHARS}>
            {running ? 'Running...' : 'Run test'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default PiiPreviewDialog;
