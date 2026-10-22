import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { INFERENCE_ENGINE_TYPES, LLM_PROVIDERS_CONFIG, type InferenceEngineType } from '@app/config/llm-providers';

interface ProviderSelectProps {
  value: InferenceEngineType;
  onChange: (provider: InferenceEngineType) => void;
  disabled?: boolean;
}

export function ProviderSelect({ value, onChange, disabled }: ProviderSelectProps) {
  return (
    <Select
      value={value}
      onValueChange={(v) => {
        if (v) onChange(v as InferenceEngineType);
      }}
      disabled={disabled}
    >
      <SelectTrigger>
        <SelectValue placeholder="Select a provider" />
      </SelectTrigger>
      <SelectContent>
        {INFERENCE_ENGINE_TYPES.map((type) => (
          <SelectItem key={type} value={type}>
            <span className="flex items-center gap-2">
              {LLM_PROVIDERS_CONFIG[type].name}
              {!LLM_PROVIDERS_CONFIG[type].voiceSupported && (
                <span className="frost-text-muted text-xs">· chatbots and agents only</span>
              )}
              {LLM_PROVIDERS_CONFIG[type].chatSupported === false && (
                <span className="frost-text-muted text-xs">· voice agents only</span>
              )}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
