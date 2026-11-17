import React from 'react';
import { Node } from '@xyflow/react';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { Switch } from '@app/components/ui/switch';
import MultiSelect from '@app/components/MultiSelect';
import { isExecutableNode } from '../graphUtils';
import {
  API_SERVICE_FUNCTION,
  DEFAULT_MAX_RETRIES,
  DEFAULT_RETRY_WINDOW_SECONDS,
  MAX_RETRIES_CAP,
  formatDuration,
  readRetrySettings,
  retryDelays,
  waitBudgetSeconds,
} from './apiServiceRetry';
import { NumberInput } from './NumberInput';
import { NodePropertiesProps, ToolOption } from './types';

interface FunctionPropertiesProps extends NodePropertiesProps {
  tools: ToolOption[];
}

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const formatParams = (params: unknown): string => {
  if (isPlainObject(params)) return JSON.stringify(params, null, 2);
  return typeof params === 'string' ? params : '';
};

export const FunctionProperties = ({ selectedNode, handleChange, nodes, tools }: FunctionPropertiesProps) => {
  // prefilled_params must be a mapping at runtime: keep the text locally and only store it once it parses to an object
  const [paramsText, setParamsText] = React.useState(() => formatParams(selectedNode.data.prefilled_params));
  const [paramsError, setParamsError] = React.useState<string | null>(null);

  const handleParamsChange = (text: string) => {
    setParamsText(text);
    if (!text.trim()) {
      setParamsError(null);
      handleChange('prefilled_params', undefined);
      return;
    }
    try {
      const parsed = JSON.parse(text);
      if (!isPlainObject(parsed)) {
        setParamsError('Prefilled params must be a JSON object, e.g. {"key": "value"}.');
        return;
      }
      setParamsError(null);
      handleChange('prefilled_params', parsed);
    } catch {
      setParamsError('Invalid JSON. The params are not updated until this is valid.');
    }
  };

  const functionName = (selectedNode.data.function_name as string) || '';

  // Retry controls write into prefilled_params, the same object the JSON box edits, and keep
  // that box in step. undefined removes a key, so the backend default applies.
  const storedParams = isPlainObject(selectedNode.data.prefilled_params) ? selectedNode.data.prefilled_params : {};
  const updateParams = (patch: Record<string, unknown>) => {
    const next: Record<string, unknown> = { ...storedParams, ...patch };
    for (const key of Object.keys(patch)) if (patch[key] === undefined) delete next[key];
    setParamsText(formatParams(next));
    setParamsError(null);
    handleChange('prefilled_params', Object.keys(next).length ? next : undefined);
  };
  const retry = readRetrySettings(storedParams);
  const waits = retryDelays(retry.maxRetries, retry.windowSeconds);
  const storedWindowSeconds = storedParams.retry_window_seconds;

  return (
    <>
      <div>
        <Label className="mb-1 block text-xs">Function Registry Name</Label>
        <Input
          list="tools-list"
          className="bg-background border-border focus:border-primary text-foreground w-full rounded-md border px-2 py-1.5 text-xs font-medium focus:outline-none"
          value={functionName}
          onChange={(e) => handleChange('function_name', e.target.value)}
          placeholder="Select or type a function name..."
          aria-invalid={!functionName}
        />
        <datalist id="tools-list">
          {tools.map((t: { name: string }) => (
            <option key={t.name} value={t.name} />
          ))}
        </datalist>
        <p className={`mt-0.5 text-[10px] ${functionName ? 'text-muted-foreground' : 'text-destructive'}`}>
          {functionName
            ? 'Exact callable name registered in the backend function registry.'
            : 'Required: the workflow cannot run until a registered function is set.'}
        </p>
      </div>
      <div>
        <Label className="mb-1 block text-xs">Description</Label>
        <textarea
          className="bg-background border-border focus:border-primary text-foreground h-16 w-full resize-none rounded-md border px-3 py-2 text-xs focus:outline-none"
          value={(selectedNode.data.description as string) || ''}
          onChange={(e) => handleChange('description', e.target.value)}
          placeholder="What this function node calculates or executes..."
        />
      </div>
      <div>
        <Label className="mb-1 block text-xs">Input Filter</Label>
        <MultiSelect
          items={nodes.filter((n) => n.id !== selectedNode.id && isExecutableNode(n))}
          selectedIds={Array.isArray(selectedNode.data.input_filter) ? selectedNode.data.input_filter : []}
          onChange={(ids) => handleChange('input_filter', ids.length > 0 ? ids : undefined)}
          getId={(n: Node) => n.id}
          getLabel={(n: Node) => (n.data?.label as string) || n.id}
          placeholder="Select upstream nodes..."
          searchPlaceholder="Search nodes..."
        />
        <p className="text-muted-foreground mt-0.5 text-[10px]">Nodes whose outputs this function consumes.</p>
      </div>
      <div>
        <Label className="mb-1 block text-xs">Prefilled Params (JSON)</Label>
        <textarea
          className={`bg-background focus:border-primary text-foreground h-24 w-full resize-none rounded-md border px-3 py-2 font-mono text-xs focus:outline-none ${paramsError ? 'border-destructive' : 'border-border'}`}
          value={paramsText}
          onChange={(e) => handleParamsChange(e.target.value)}
          aria-invalid={!!paramsError}
          placeholder='{\n  "message_processor_id": "123"\n}'
        />
        {paramsError && <p className="text-destructive mt-0.5 text-[10px]">{paramsError}</p>}
      </div>
      {functionName === API_SERVICE_FUNCTION && (
        // Every control here rebuilds the JSON box from the stored params, so they are all
        // disabled while it holds a half-typed edit that is not valid yet.
        <fieldset
          disabled={!!paramsError}
          className="border-border min-w-0 space-y-2 rounded-md border p-2 disabled:opacity-60"
        >
          <div className="flex items-center justify-between gap-2">
            <Label htmlFor="api-service-retry" className="text-xs">
              Retry on failure
            </Label>
            <Switch
              id="api-service-retry"
              checked={retry.enabled}
              onCheckedChange={(on) =>
                updateParams(
                  on
                    ? {
                        retry_enabled: true,
                        max_retries: storedParams.max_retries ?? DEFAULT_MAX_RETRIES,
                        retry_window_seconds: storedParams.retry_window_seconds ?? DEFAULT_RETRY_WINDOW_SECONDS,
                      }
                    : { retry_enabled: undefined, max_retries: undefined, retry_window_seconds: undefined }
                )
              }
            />
          </div>
          {retry.enabled ? (
            <>
              <div className="flex gap-2">
                <div className="flex-1">
                  <Label className="mb-1 block text-xs">Retries</Label>
                  <NumberInput
                    min={0}
                    max={MAX_RETRIES_CAP}
                    step={1}
                    placeholder={String(DEFAULT_MAX_RETRIES)}
                    value={storedParams.max_retries}
                    onChange={(v) => updateParams({ max_retries: v === undefined ? undefined : Math.round(v) })}
                    className="bg-background h-8 text-xs"
                  />
                </div>
                <div className="flex-1">
                  <Label className="mb-1 block text-xs">Retry window (minutes)</Label>
                  <NumberInput
                    min={0}
                    step={1}
                    placeholder={String(DEFAULT_RETRY_WINDOW_SECONDS / 60)}
                    value={storedWindowSeconds === undefined ? undefined : Number(storedWindowSeconds) / 60}
                    onChange={(v) =>
                      updateParams({ retry_window_seconds: v === undefined ? undefined : Math.round(v * 60) })
                    }
                    className="bg-background h-8 text-xs"
                  />
                </div>
              </div>
              <p className="text-foreground text-[10px]">
                {retry.windowSeconds > 0 && retry.maxRetries > 0
                  ? `Never holds the run longer than ${formatDuration(retry.windowSeconds)}, even if every attempt fails.`
                  : 'No retries: one attempt only.'}
              </p>
              <p className="text-muted-foreground text-[10px]">
                {retry.windowSeconds > 0 && retry.maxRetries > 0
                  ? waitBudgetSeconds(retry.maxRetries, retry.windowSeconds) > 0
                    ? `Waits between attempts: ${waits.map(formatDuration).join(', ')}. Each attempt can take up to 60s.`
                    : 'The window is too short to wait between retries: attempts run back to back, as many as fit.'
                  : ''}{' '}
                Retried: no answer, timeouts, HTTP 408, 429 and 5xx. Any other answer returns at once.
                {Number(storedParams.max_retries) > MAX_RETRIES_CAP ? ` Retries are capped at ${MAX_RETRIES_CAP}.` : ''}
              </p>
            </>
          ) : (
            <p className="text-muted-foreground text-[10px]">
              Off: one attempt. A failure is returned as the node&apos;s output and the run continues.
            </p>
          )}
          {paramsError && <p className="text-muted-foreground text-[10px]">Fix the JSON above to change retries.</p>}
        </fieldset>
      )}
    </>
  );
};
