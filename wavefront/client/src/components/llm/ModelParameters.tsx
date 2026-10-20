import { ChevronDown, RotateCcw } from 'lucide-react';
import { useState } from 'react';

import FieldHelp from '@app/components/FieldHelp';
import { Alert, AlertDescription } from '@app/components/ui/alert';
import { Checkbox } from '@app/components/ui/checkbox';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Slider } from '@app/components/ui/slider';
import {
  findModelPreset,
  getModelGroups,
  getModelParameters,
  getParameterLabel,
  isParameterActive,
} from '@app/config/llm-models';
import {
  getProviderConfig,
  type InferenceEngineType,
  type ParameterConfig,
  UNSET_SELECT_VALUE,
} from '@app/config/llm-providers';
import { cn } from '@app/lib/utils';

interface ModelParametersProps {
  provider: InferenceEngineType;
  modelId: string;
  values: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
  disabled?: boolean;
  /** Saved settings this model does not accept; they are removed on the next save. */
  droppedKeys?: string[];
}

/**
 * The settings the chosen model accepts. An empty field is left out of the
 * request, so the provider's default applies.
 */
export function ModelParameters({ provider, modelId, values, onChange, disabled, droppedKeys }: ModelParametersProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const preset = findModelPreset(provider, modelId);
  const allParams = getModelParameters(provider, modelId);
  const params = allParams.filter(([, config]) => isParameterActive(config, allParams, values));
  // Settings the chosen reasoning effort switches off, so the field doesn't just vanish
  const inactive = allParams.filter(([, config]) => !isParameterActive(config, allParams, values));
  const basic = params.filter(([, config]) => !config.advanced);
  const advanced = params.filter(([, config]) => config.advanced);
  const advancedSet = advanced.filter(([key]) => values[key] !== undefined).length;
  const providerConfig = getProviderConfig(provider);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        {!providerConfig?.voiceSupported && (
          <Alert variant="info">
            <AlertDescription>
              Voice agents can&apos;t use {providerConfig?.name}. It works for chatbots and agents.
            </AlertDescription>
          </Alert>
        )}
        {preset?.note && (
          <Alert variant="info">
            <AlertDescription>{preset.note}</AlertDescription>
          </Alert>
        )}
        {modelId.trim() && !preset && getModelGroups(provider).length > 0 && (
          <Alert variant="default">
            <AlertDescription>
              This model isn&apos;t in the list, so every {providerConfig?.name} setting is shown. Set only the ones
              your model supports; an unsupported one fails the request.
            </AlertDescription>
          </Alert>
        )}
        {inactive.length > 0 && (
          <Alert variant="default">
            <AlertDescription>
              {inactive.map(([, c]) => c.label).join(' and ')} {inactive.length > 1 ? 'are' : 'is'} only available when{' '}
              {getParameterLabel(provider, inactive[0]![1].activeWhen!.key).toLowerCase()} is{' '}
              {inactive[0]![1].activeWhen!.equals === 'none' ? 'None' : inactive[0]![1].activeWhen!.equals}
              {inactive.some(([key]) => values[key] !== undefined) && '; the values you set are removed on save'}.
            </AlertDescription>
          </Alert>
        )}
        {!!droppedKeys?.length && (
          <Alert variant="default">
            <AlertDescription>
              Saved settings this model doesn&apos;t accept will be removed when you save:{' '}
              {droppedKeys.map((k) => getParameterLabel(provider, k)).join(', ')}.
            </AlertDescription>
          </Alert>
        )}
      </div>

      {params.length === 0 ? (
        <p className="frost-text-muted text-sm">This model has no adjustable settings.</p>
      ) : (
        <>
          <ParameterGrid params={basic} values={values} onChange={onChange} disabled={disabled} />
          {advanced.length > 0 && (
            <div className="flex flex-col gap-4">
              <button
                type="button"
                onClick={() => setShowAdvanced((v) => !v)}
                className="frost-text-muted hover:text-frost-text flex w-fit cursor-pointer items-center gap-1 text-sm font-medium"
              >
                <ChevronDown className={cn('h-4 w-4 transition-transform', showAdvanced && 'rotate-180')} />
                Advanced settings
                {advancedSet > 0 && !showAdvanced && <span className="text-xs">({advancedSet} set)</span>}
              </button>
              {showAdvanced && (
                <ParameterGrid params={advanced} values={values} onChange={onChange} disabled={disabled} />
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

interface ParameterGridProps {
  params: Array<[string, ParameterConfig]>;
  values: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
  disabled?: boolean;
}

function ParameterGrid({ params, values, onChange, disabled }: ParameterGridProps) {
  return (
    <div className="grid w-full gap-x-6 gap-y-5 sm:grid-cols-2 xl:grid-cols-3">
      {params.map(([key, config]) => (
        <ParameterField
          key={key}
          paramKey={key}
          config={config}
          value={values[key]}
          onChange={(value) => onChange(key, value)}
          disabled={disabled}
        />
      ))}
    </div>
  );
}

interface ParameterFieldProps {
  paramKey: string;
  config: ParameterConfig;
  value: unknown;
  onChange: (value: unknown) => void;
  disabled?: boolean;
}

function ParameterField({ paramKey, config, value, onChange, disabled }: ParameterFieldProps) {
  const isSet = value !== undefined && value !== null && value !== '';
  const defaultLabel = describeDefault(config);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex min-h-5 items-center justify-between gap-2">
        <label htmlFor={`param-${paramKey}`} className="frost-text flex items-center gap-1.5 text-sm font-medium">
          {config.label}
          {config.description && <FieldHelp ariaLabel={`About ${config.label}`}>{config.description}</FieldHelp>}
        </label>
        {isSet && !disabled && config.type !== 'select' && (
          <button
            type="button"
            onClick={() => onChange(undefined)}
            className="frost-text-muted hover:text-frost-text flex cursor-pointer items-center gap-1 text-xs"
            aria-label={`Reset ${config.label} to default`}
          >
            <RotateCcw className="h-3 w-3" />
            Default
          </button>
        )}
      </div>

      {config.type === 'number' && (
        <div className="flex flex-col gap-2">
          <Input
            id={`param-${paramKey}`}
            type="number"
            value={typeof value === 'number' || typeof value === 'string' ? value : ''}
            onChange={(e) => onChange(e.target.value === '' ? undefined : parseFloat(e.target.value))}
            min={config.min}
            max={config.max}
            step={config.step}
            placeholder={defaultLabel ?? config.placeholder ?? 'Default'}
            disabled={disabled}
          />
          {config.min !== undefined && config.max !== undefined && config.max - config.min <= 10 && (
            <Slider
              value={[
                typeof value === 'number' ? value : typeof config.default === 'number' ? config.default : config.min,
              ]}
              onValueChange={(values) => onChange(values[0])}
              min={config.min}
              max={config.max}
              step={config.step}
              disabled={disabled}
              className={cn(!isSet && 'opacity-50')}
            />
          )}
        </div>
      )}

      {config.type === 'select' && config.options && (
        <Select
          value={isSet ? String(value) : UNSET_SELECT_VALUE}
          onValueChange={(v) => {
            if (!v) return;
            onChange(v === UNSET_SELECT_VALUE ? undefined : v);
          }}
          disabled={disabled}
        >
          <SelectTrigger id={`param-${paramKey}`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={UNSET_SELECT_VALUE}>{defaultLabel ?? 'Provider default'}</SelectItem>
            {config.options.map((option) => (
              <SelectItem key={String(option.value)} value={String(option.value)}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {config.type === 'boolean' && (
        <div className="flex h-9 items-center gap-2">
          <Checkbox
            id={`param-${paramKey}`}
            checked={value === true}
            onCheckedChange={(checked) => onChange(checked === true ? true : undefined)}
            disabled={disabled}
          />
          <span className="frost-text text-sm">Enable</span>
        </div>
      )}

      {config.type === 'string' && (
        <Input
          id={`param-${paramKey}`}
          type="text"
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(e.target.value || undefined)}
          placeholder={config.placeholder ?? 'Default'}
          disabled={disabled}
        />
      )}
    </div>
  );
}

/** "Default (Medium)" / "Default (1)", or nothing when the default isn't documented. */
function describeDefault(config: ParameterConfig): string | undefined {
  if (config.default === undefined) return undefined;
  const option = config.options?.find((o) => String(o.value) === String(config.default));
  return `Default (${option?.label ?? String(config.default)})`;
}
