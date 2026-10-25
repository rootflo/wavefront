import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Checkbox } from '@app/components/ui/checkbox';
import { Label } from '@app/components/ui/label';
import { Slider } from '@app/components/ui/slider';
import { getProviderConfig } from '@app/config/voice-providers';
import {
  getBooleanParameterWithDefault,
  getNumberOrStringParameter,
  getNumberParameterWithDefault,
  getStringParameter,
} from '@app/utils/parameter-helpers';

import { ParameterKind } from './voice-agent-form';

export interface ParameterState {
  provider?: string;
  values: Record<string, unknown>;
  set: (key: string, value: unknown) => void;
}

/** One provider setting (TTS or STT), drawn from the provider's parameter config. */
const ProviderParameterField = ({
  kind,
  paramKey: key,
  provider,
  values,
  set,
}: { kind: ParameterKind; paramKey: string } & ParameterState) => {
  if (!provider) return null;
  const paramConfig = getProviderConfig(kind, provider)?.parameters[key];
  if (!paramConfig) return null;
  const id = `${kind}-${key}`;
  const label = paramConfig.description || key;

  switch (paramConfig.type) {
    case 'boolean':
      return (
        <div key={key} className="flex items-center space-x-2">
          <Checkbox
            id={id}
            checked={getBooleanParameterWithDefault(values, key, paramConfig.default)}
            onCheckedChange={(checked) => set(key, checked)}
          />
          <Label htmlFor={id} className="frost-text-muted cursor-pointer">
            {label}
          </Label>
        </div>
      );

    case 'number': {
      if (paramConfig.min !== undefined && paramConfig.max !== undefined) {
        const sliderValue = getNumberParameterWithDefault(values, key, paramConfig.default, paramConfig.min);
        return (
          <div key={key} className="space-y-2">
            <Label className="frost-text-muted">
              {label}: {Number.isInteger(sliderValue) ? sliderValue : sliderValue.toFixed(2)}
            </Label>
            <Slider
              min={paramConfig.min}
              max={paramConfig.max}
              step={paramConfig.step || 1}
              value={[sliderValue]}
              onValueChange={(next: number[]) => set(key, next[0])}
            />
          </div>
        );
      }

      // STT numbers are whole values (sample rates, milliseconds)
      const parse = kind === 'stt' ? parseInt : parseFloat;
      return (
        <div key={key} className="space-y-2">
          <Label htmlFor={id} className="frost-text-muted">
            {label}
          </Label>
          <Input
            id={id}
            type="number"
            value={getNumberOrStringParameter(values, key)}
            // Clearing the field leaves the setting unset, so the provider's default applies
            onChange={(e) => set(key, e.target.value ? parse(e.target.value) : undefined)}
            placeholder={paramConfig.placeholder}
            step={paramConfig.step}
          />
          {paramConfig.placeholder && (
            <p className="text-muted-foreground text-[0.8rem]">e.g., {paramConfig.placeholder}</p>
          )}
        </div>
      );
    }

    case 'string':
    default: {
      // Language comes from the agent's supported languages, not a provider setting
      if (key === 'language') return null;

      if (paramConfig.options && paramConfig.options.length > 0) {
        const current = getStringParameter(values, key);
        const selectValue =
          current ||
          (paramConfig.default !== undefined && paramConfig.default !== '' ? String(paramConfig.default) : undefined);
        return (
          <div key={key} className="space-y-2">
            <Label htmlFor={id} className="frost-text-muted">
              {label}
            </Label>
            <Select value={selectValue} onValueChange={(val) => set(key, val)}>
              <SelectTrigger id={id}>
                <SelectValue placeholder="Select..." />
              </SelectTrigger>
              <SelectContent>
                {paramConfig.options.map((option) => (
                  <SelectItem key={String(option)} value={String(option)}>
                    {String(option)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        );
      }

      return (
        <div key={key} className="space-y-2">
          <Label htmlFor={id} className="frost-text-muted">
            {label}
          </Label>
          <Input
            id={id}
            type="text"
            value={getStringParameter(values, key)}
            onChange={(e) => set(key, e.target.value)}
            placeholder={paramConfig.placeholder}
          />
          {paramConfig.placeholder && (
            <p className="text-muted-foreground text-[0.8rem]">Default: {paramConfig.placeholder}</p>
          )}
        </div>
      );
    }
  }
};

export default ProviderParameterField;
