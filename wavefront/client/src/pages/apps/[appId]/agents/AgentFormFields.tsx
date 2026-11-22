import { Button } from '@app/components/ui/button';
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Slider } from '@app/components/ui/slider';
import { Textarea } from '@app/components/ui/textarea';
import type { LLMInferenceConfig } from '@app/types/llm-inference-config';
import React, { useEffect, useMemo, useState } from 'react';
import { useFormContext, useWatch } from 'react-hook-form';
import { Link } from 'react-router';
import { getAgentModelInfo, ROOTFLO_PROVIDER, switchModelToRootflo } from './agentYamlMapper';
import { ACT_AS_OPTIONS, REASONING_PATTERNS, TEMPERATURE_RANGE, type AgentFormValues } from './schemas';

// Select items cannot have an empty value, so "no reasoning pattern" (provider default) uses a sentinel.
const DEFAULT_REASONING_PATTERN = '__default__';
// Where the temperature slider rests while no temperature is set (the provider default applies).
const TEMPERATURE_SLIDER_REST = 0.7;
const DEFAULT_ACT_AS = 'assistant';

const NUMBER_PATTERN = /^-?(\d+\.?\d*|\.\d+)$/;

const formatNumber = (value: number | null | undefined): string => (value == null ? '' : String(value));

/** The number typed so far, null for an empty field, or undefined while the text is not a complete number. */
const parseNumberText = (text: string): number | null | undefined => {
  const trimmed = text.trim();
  if (trimmed === '') return null;
  return NUMBER_PATTERN.test(trimmed) ? Number(trimmed) : undefined;
};

type NumberInputProps = Omit<React.ComponentProps<typeof Input>, 'value' | 'onChange' | 'type'> & {
  value: number | null | undefined;
  onChange: (value: number | null) => void;
};

/**
 * Numeric input that keeps the text being typed, so intermediate input such as "0." or "-" is not wiped out,
 * and shows a stored 0 as "0" rather than as an empty field. Clearing the field commits null.
 */
const NumberInput = ({ value, onChange, onBlur, ...props }: NumberInputProps) => {
  const [text, setText] = useState(() => formatNumber(value));

  // Follow changes made outside the input (YAML -> form) unless the text already represents the value.
  useEffect(() => {
    setText((current) => (parseNumberText(current) === (value ?? null) ? current : formatNumber(value)));
  }, [value]);

  return (
    <Input
      {...props}
      type="text"
      inputMode="decimal"
      value={text}
      onChange={(event) => {
        setText(event.target.value);
        const parsed = parseNumberText(event.target.value);
        if (parsed !== undefined) onChange(parsed);
      }}
      onBlur={(event) => {
        // Drop incomplete text (e.g. "-") so the field shows what is actually stored.
        setText(formatNumber(value));
        onBlur?.(event);
      }}
    />
  );
};

type NumberFieldName = 'maxTokens' | 'topK' | 'topP' | 'frequencyPenalty' | 'presencePenalty' | 'seed';

const NumberField = ({ name, label, placeholder }: { name: NumberFieldName; label: string; placeholder: string }) => {
  const { control } = useFormContext<AgentFormValues>();
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel className="frost-text">{label}</FormLabel>
          <FormControl>
            <NumberInput
              placeholder={placeholder}
              className="frost-control"
              name={field.name}
              ref={field.ref}
              value={field.value}
              onChange={field.onChange}
              onBlur={field.onBlur}
            />
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
};

const ModelField = ({ appId, llmConfigs }: { appId?: string; llmConfigs: LLMInferenceConfig[] }) => {
  const { control, setValue, clearErrors } = useFormContext<AgentFormValues>();
  const yamlContent = useWatch({ control, name: 'yamlContent' });
  const modelInfo = useMemo(() => getAgentModelInfo(yamlContent), [yamlContent]);
  const provider = modelInfo?.provider ?? '';

  if (provider && provider !== ROOTFLO_PROVIDER) {
    // Other providers are edited in YAML; the RootFlo picker must never silently replace their model block.
    return (
      <FormField
        control={control}
        name="modelId"
        render={() => (
          <FormItem className="col-span-2">
            <FormLabel className="frost-text">LLM Model</FormLabel>
            <div className="frost-control border-frost-border flex flex-wrap items-center justify-between gap-3 rounded-md border px-3 py-2">
              <p className="frost-text text-sm">
                Configured in YAML: <span className="font-medium">{provider}</span>
                {modelInfo?.name ? ` / ${modelInfo.name}` : ''}
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setValue('yamlContent', switchModelToRootflo(yamlContent), { shouldDirty: true });
                  setValue('modelId', '');
                  clearErrors('modelId');
                }}
              >
                Use a model from the Model Hub instead
              </Button>
            </div>
            <p className="frost-text-muted text-xs">Edit provider settings for this model in the YAML tab.</p>
            <FormMessage />
          </FormItem>
        )}
      />
    );
  }

  return (
    <FormField
      control={control}
      name="modelId"
      render={({ field }) => {
        const isKnownConfig = llmConfigs.some((config) => config.id === field.value);
        return (
          <FormItem className="col-span-2">
            <FormLabel className="frost-text">
              LLM Model <span className="text-red-500">*</span>
            </FormLabel>
            {/* Radix Select can report '' while its options load; only a real choice is an edit. */}
            <Select onValueChange={(value) => value && field.onChange(value)} value={field.value || ''}>
              <FormControl>
                <SelectTrigger className="frost-control">
                  <SelectValue placeholder="Select a RootFlo LLM model" />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                {field.value && !isKnownConfig && (
                  <SelectItem value={field.value}>Unavailable model ({field.value})</SelectItem>
                )}
                {llmConfigs.map((config) => (
                  <SelectItem key={config.id} value={config.id}>
                    {config.display_name || config.llm_model || config.id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {llmConfigs.length === 0 && (
              <p className="frost-text-muted text-xs">
                No models in the Model Hub yet.{' '}
                {appId && (
                  <Link to={`/apps/${appId}/model-hub`} className="text-primary underline">
                    Add one
                  </Link>
                )}
              </p>
            )}
            <FormMessage />
          </FormItem>
        );
      }}
    />
  );
};

export type AgentFormSection = 'identity' | 'model' | 'advanced';

interface AgentFormFieldsProps {
  /** Render only one section (one per tab in the create dialog); all three are shown when omitted. */
  section?: AgentFormSection;
  appId?: string;
  llmConfigs: LLMInferenceConfig[];
  /** Dialog-specific identity fields rendered first (e.g. agent id and namespace on create). */
  identityFields?: React.ReactNode;
  /** Renders the editable agent.name field. */
  showAgentName?: boolean;
  /** Rendered next to the tags field (e.g. the tools picker on edit). */
  toolsField?: React.ReactNode;
}

/**
 * The builder tab shared by the Create and Edit agent dialogs. Must be rendered inside <Form> whose form is
 * driven by useAgentYamlForm, which turns each field edit into a patch of the agent YAML.
 */
const AgentFormFields: React.FC<AgentFormFieldsProps> = ({
  appId,
  llmConfigs,
  identityFields,
  section,
  showAgentName = false,
  toolsField,
}) => {
  const { control } = useFormContext<AgentFormValues>();

  return (
    <>
      {/* METADATA SECTION */}
      {!section || section === 'identity' ? (
        <section className="space-y-4">
          {!section && <h3 className="frost-text flex items-center gap-2 text-lg font-medium">Identity & Metadata</h3>}

          <div
            className={section ? 'space-y-6' : 'frost-card ring-frost-border space-y-6 rounded-2xl border p-6 ring-1'}
          >
            {identityFields}

            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              {showAgentName && (
                <FormField
                  control={control}
                  name="agentName"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="frost-text">
                        Display Name (agent.name) <span className="text-red-500">*</span>
                      </FormLabel>
                      <FormControl>
                        <Input placeholder="my-agent" className="frost-control" {...field} value={field.value ?? ''} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              <FormField
                control={control}
                name="role"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="frost-text">Role</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="e.g. Senior Software Engineer"
                        className="frost-control"
                        {...field}
                        value={field.value ?? ''}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={control}
                name="actAs"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="frost-text">Act As</FormLabel>
                    {/* flo_ai defaults act_as to assistant; '' from Radix is not a user choice. */}
                    <Select
                      onValueChange={(value) => value && field.onChange(value)}
                      value={field.value || DEFAULT_ACT_AS}
                    >
                      <FormControl>
                        <SelectTrigger className="frost-control">
                          <SelectValue placeholder="Select act as" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {ACT_AS_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="frost-text">Description</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="e.g. Translates text into the requested tone"
                        className="frost-control"
                        {...field}
                        value={field.value ?? ''}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={control}
                name="tags"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="frost-text">Tags (Comma Separated)</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="e.g. translation, support"
                        className="frost-control"
                        {...field}
                        value={field.value ?? ''}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {toolsField}
            </div>

            <FormField
              control={control}
              name="job"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="frost-text">
                    System Prompt / Job <span className="text-red-500">*</span>
                  </FormLabel>
                  <FormControl>
                    <Textarea
                      rows={4}
                      placeholder="e.g. You are a translator. Translate the user's text using this tone: <tone>"
                      className="frost-control"
                      {...field}
                      value={field.value ?? ''}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        </section>
      ) : null}

      {/* MODEL CONFIGURATION SECTION */}
      {!section || section === 'model' ? (
        <section className="space-y-4">
          {!section && <h3 className="frost-text flex items-center gap-2 text-lg font-medium">Model Configuration</h3>}

          <div
            className={section ? 'space-y-6' : 'frost-card ring-frost-border space-y-6 rounded-2xl border p-6 ring-1'}
          >
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              <ModelField appId={appId} llmConfigs={llmConfigs} />
            </div>
          </div>
        </section>
      ) : null}

      {/* ADVANCED SETTINGS SECTION */}
      {!section || section === 'advanced' ? (
        <section className="space-y-4">
          {!section && (
            <h3 className="frost-text flex items-center gap-2 text-lg font-medium">Advanced Generation Settings</h3>
          )}

          <div
            className={section ? 'space-y-6' : 'frost-card ring-frost-border space-y-6 rounded-2xl border p-6 ring-1'}
          >
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              <FormField
                control={control}
                name="temperature"
                render={({ field }) => (
                  <FormItem>
                    <div className="mb-2 flex items-center justify-between">
                      <FormLabel className="frost-text m-0">Temperature</FormLabel>
                      <div className="flex items-center gap-2">
                        <span className="frost-text-muted text-xs">{field.value ?? 'Default'}</span>
                        {field.value != null && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="h-auto px-1 py-0 text-xs"
                            onClick={() => field.onChange(null)}
                          >
                            Reset
                          </Button>
                        )}
                      </div>
                    </div>
                    <FormControl>
                      <Slider
                        min={TEMPERATURE_RANGE.min}
                        max={TEMPERATURE_RANGE.max}
                        step={TEMPERATURE_RANGE.step}
                        value={[field.value ?? TEMPERATURE_SLIDER_REST]}
                        onValueChange={(value) => field.onChange(value[0])}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={control}
                name="reasoningPattern"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="frost-text">Reasoning Pattern</FormLabel>
                    <Select
                      onValueChange={(value) => {
                        if (!value) return;
                        field.onChange(value === DEFAULT_REASONING_PATTERN ? '' : value);
                      }}
                      value={field.value || DEFAULT_REASONING_PATTERN}
                    >
                      <FormControl>
                        <SelectTrigger className="frost-control">
                          <SelectValue placeholder="Select pattern" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value={DEFAULT_REASONING_PATTERN}>Default</SelectItem>
                        {REASONING_PATTERNS.map((pattern) => (
                          <SelectItem key={pattern.value} value={pattern.value}>
                            {pattern.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
              <NumberField name="maxTokens" label="Max Tokens" placeholder="Default" />
              <NumberField name="topK" label="Top K" placeholder="Default" />
              <NumberField name="topP" label="Top P (0.0 to 1.0)" placeholder="Default" />
            </div>

            <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
              <NumberField name="frequencyPenalty" label="Freq. Penalty" placeholder="Default" />
              <NumberField name="presencePenalty" label="Pres. Penalty" placeholder="Default" />
              <NumberField name="seed" label="Seed" placeholder="Random" />
            </div>
          </div>
        </section>
      ) : null}
    </>
  );
};

export default AgentFormFields;
