import { FailureMode, GuardrailAdapterConfig, PiiEntityGroup, WorkflowStage } from '@app/api/guardrails-service';
import { Button } from '@app/components/ui/button';
import { Checkbox } from '@app/components/ui/checkbox';
import { Label } from '@app/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Separator } from '@app/components/ui/separator';
import { Slider } from '@app/components/ui/slider';
import { Switch } from '@app/components/ui/switch';
import React, { useState } from 'react';
import PiiEntitySelector from './PiiEntitySelector';
import PiiPreviewDialog from './PiiPreviewDialog';
import { ADAPTER_META, SEVERITY_LABELS, STAGE_LABELS } from './adapter-meta';

interface Props {
  name: string;
  config?: GuardrailAdapterConfig;
  disabled: boolean;
  onToggle: (enabled: boolean) => void;
  onChange: (patch: Partial<GuardrailAdapterConfig>) => void;
  /** Entity catalog from the server. Only meaningful for the PII adapter. */
  piiGroups?: PiiEntityGroup[];
}

const AdapterCard: React.FC<Props> = ({ name, config, disabled, onToggle, onChange, piiGroups }) => {
  const meta = ADAPTER_META[name];
  const enabled = !!config;
  const [testing, setTesting] = useState(false);

  const toggleStage = (stage: WorkflowStage, checked: boolean) => {
    if (!config) return;
    const stages = checked ? [...config.stages, stage] : config.stages.filter((item) => item !== stage);
    // A check with no stages would be saved but never invoked, which reads as
    // "configured and working" while doing nothing.
    onChange({ stages: stages.length ? stages : config.stages });
  };

  const setOption = (key: string, value: unknown) => {
    if (!config) return;
    onChange({ options: { ...config.options, [key]: value } });
  };

  const severity = Number(config?.options?.severity_threshold ?? 4);

  return (
    <section className={`rounded-lg border border-gray-200 p-6 ${disabled ? 'opacity-60' : ''}`}>
      <div className="flex items-start justify-between">
        <div className="pr-8">
          <Label className="text-base font-semibold">{meta?.title ?? name}</Label>
          <p className="mt-1 text-sm text-gray-600">{meta?.description ?? name}</p>
        </div>
        <Switch checked={enabled} disabled={disabled} onCheckedChange={onToggle} />
      </div>

      {enabled && config && (
        <>
          <Separator className="my-6" />

          <div className="flex flex-col gap-5">
            <div>
              <Label className="text-sm font-medium">Where it runs</Label>
              <div className="mt-2 flex flex-col gap-2">
                {(Object.keys(STAGE_LABELS) as WorkflowStage[]).map((stage) => (
                  <label key={stage} className="flex items-center gap-2 text-sm text-gray-700">
                    <Checkbox
                      checked={config.stages.includes(stage)}
                      disabled={disabled}
                      onCheckedChange={(checked) => toggleStage(stage, checked === true)}
                    />
                    {STAGE_LABELS[stage]}
                  </label>
                ))}
              </div>
            </div>

            {name === 'presidio_pii' && (piiGroups?.length ?? 0) === 0 && (
              <p className="rounded-md border border-dashed border-gray-300 bg-gray-50 p-3 text-xs text-gray-600">
                The list of detectable identifiers could not be loaded, so there is nothing to choose from here. This
                check keeps running with its default set of high-precision identifiers — emails, phone numbers, card
                numbers and similar.
              </p>
            )}

            {name === 'presidio_pii' && (piiGroups?.length ?? 0) > 0 && (
              <>
                <PiiEntitySelector
                  groups={piiGroups!}
                  selected={config.options?.entities as string[] | undefined}
                  disabled={disabled}
                  onChange={(entities) => setOption('entities', entities)}
                />
                <div className="flex items-center justify-between">
                  <p className="pr-8 text-xs text-gray-500">
                    Check the selection against sample text before switching this namespace to Enforce.
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={disabled}
                    onClick={() => setTesting(true)}
                  >
                    Test policy
                  </Button>
                </div>
                <PiiPreviewDialog
                  open={testing}
                  onOpenChange={setTesting}
                  options={(config.options ?? {}) as Record<string, unknown>}
                  groups={piiGroups}
                />
              </>
            )}

            {name === 'azure_content_safety' && (
              <>
                <div>
                  <div className="flex items-center justify-between">
                    <Label className="text-sm font-medium">Block at severity</Label>
                    <span className="text-sm text-gray-600">{SEVERITY_LABELS[severity] ?? severity}</span>
                  </div>
                  <Slider
                    className="mt-3"
                    min={0}
                    max={6}
                    step={2}
                    value={[severity]}
                    disabled={disabled}
                    onValueChange={([value]) => setOption('severity_threshold', value)}
                  />
                  <p className="mt-2 text-xs text-gray-500">
                    Content is scored 0, 2, 4 or 6. Blocking at low rejects a large share of ordinary traffic; medium is
                    the usual starting point.
                  </p>
                </div>

                <label className="flex items-center gap-2 text-sm text-gray-700">
                  <Checkbox
                    checked={config.options?.enable_prompt_shields !== false}
                    disabled={disabled}
                    onCheckedChange={(checked) => setOption('enable_prompt_shields', checked === true)}
                  />
                  Detect prompt injection and jailbreak attempts
                </label>
              </>
            )}

            <div>
              <div className="flex items-center justify-between">
                <div className="pr-8">
                  <Label className="text-sm font-medium">If this check cannot run</Label>
                  <p className="mt-1 text-xs text-gray-500">
                    Applies to outages, timeouts and rate limiting. Content this check refuses to process — oversized or
                    non-text — is always blocked regardless of this setting.
                  </p>
                </div>
                <Select value={config.on_error} onValueChange={(value) => onChange({ on_error: value as FailureMode })}>
                  <SelectTrigger className="w-[150px]" disabled={disabled}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="FAIL_OPEN">Allow</SelectItem>
                    <SelectItem value="FAIL_CLOSED">Block</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
};

export default AdapterCard;
