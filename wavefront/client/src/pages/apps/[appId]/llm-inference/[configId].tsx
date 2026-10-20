import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { ModelParameters } from '@app/components/llm/ModelParameters';
import { ModelSelect, ModelTags } from '@app/components/llm/ModelSelect';
import { ProviderSelect } from '@app/components/llm/ProviderSelect';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import { Button } from '@app/components/ui/button';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Spinner } from '@app/components/ui/spinner';
import { filterParameters, findModelPreset } from '@app/config/llm-models';
import { getDefaultBaseUrl, getProviderConfig } from '@app/config/llm-providers';
import { useGetLLMConfig } from '@app/hooks';
import { getLLMConfigKey, getLLMConfigsKey } from '@app/hooks/data/query-keys';
import { extractErrorMessage, formatAppName } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { InferenceEngineType, LLMInferenceConfig, UpdateLLMConfigRequest } from '@app/types/llm-inference-config';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate, useParams } from 'react-router';
import { z } from 'zod';

const REQUIRES_API_KEY: InferenceEngineType[] = ['openai', 'anthropic', 'gemini', 'azure_openai', 'groq'];

const llmConfigFormSchema = z
  .object({
    display_name: z.string().min(1, 'Display name is required'),
    llm_model: z.string().min(1, 'Choose a model'),
    type: z.enum(['openai', 'anthropic', 'gemini', 'azure_openai', 'ollama', 'vllm', 'groq']),
    api_key: z.string().optional(),
    model_type: z.enum(['llm', 'embedding']),
    base_url: z.string().optional(),
    api_version: z.string().optional(),
  })
  .superRefine((data, ctx) => {
    if (data.type === 'azure_openai' && !data.api_version?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['api_version'],
        message: 'API version is required for Azure OpenAI',
      });
    }
  });

type LLMConfigForm = z.infer<typeof llmConfigFormSchema>;

/**
 * Build the complete set of form values from a saved config.
 * Shared by the initial load and the edit-cancel revert so neither can omit a
 * field: `form.reset` replaces every value, so a partial payload would silently
 * blank out whatever it left out (e.g. the Azure-only `api_version`).
 */
const buildFormValues = (config: LLMInferenceConfig): LLMConfigForm => ({
  display_name: config.display_name,
  llm_model: config.llm_model,
  type: config.type,
  model_type: (config.model_type as 'llm' | 'embedding') || 'llm',
  api_key: '', // API key is never returned for security
  base_url: config.base_url || '',
  api_version: (config.parameters?.api_version as string) || '',
});

/** The saved settings the saved model accepts. */
const savedParameters = (config: LLMInferenceConfig) =>
  filterParameters(config.type, config.llm_model, config.parameters).kept;

const SectionTitle: React.FC<{ title: string; description?: string; children?: React.ReactNode }> = ({
  title,
  description,
  children,
}) => (
  <div className="flex items-start justify-between gap-4">
    <div>
      <h3 className="frost-text text-lg font-semibold">{title}</h3>
      {description && <p className="frost-text-muted text-sm">{description}</p>}
    </div>
    {children}
  </div>
);

const LLMInferenceConfigDetail: React.FC = () => {
  const { app: appId, llmId } = useParams<{ app: string; llmId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  const { data: config, isLoading } = useGetLLMConfig(appId, llmId);

  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [parameters, setParameters] = useState<Record<string, unknown>>({});

  const form = useForm<LLMConfigForm>({
    resolver: zodResolver(llmConfigFormSchema),
    defaultValues: {
      display_name: '',
      llm_model: '',
      type: 'openai',
      model_type: 'llm',
      api_key: '',
      base_url: '',
      api_version: '',
    },
    mode: 'onChange',
  });

  const resetToSaved = (saved: LLMInferenceConfig) => {
    form.reset(buildFormValues(saved));
    setParameters(savedParameters(saved));
  };

  useEffect(() => {
    if (config) resetToSaved(config);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  const type = form.watch('type');
  const llmModel = form.watch('llm_model');
  const modelType = form.watch('model_type');
  const providerConfig = getProviderConfig(type);
  const preset = findModelPreset(type, llmModel);
  // Settings saved on this config that the current model rejects; the next save drops them.
  const dropped = config ? filterParameters(type, llmModel, config.parameters).dropped : [];

  const changeProvider = (newType: InferenceEngineType) => {
    form.setValue('type', newType, { shouldValidate: true });
    form.setValue('base_url', getDefaultBaseUrl(newType));
    setParameters((prev) => filterParameters(newType, form.getValues('llm_model'), prev).kept);
  };

  const changeModel = (modelId: string) => {
    form.setValue('llm_model', modelId, { shouldValidate: true });
    setParameters((prev) => filterParameters(type, modelId, prev).kept);
  };

  const handleSave = async (data: LLMConfigForm) => {
    if (!llmId || !config) return;

    setSaving(true);
    try {
      // Only what this model accepts goes out, so a stale or unsupported setting cannot fail requests
      const { kept } = filterParameters(data.type, data.llm_model, data.model_type === 'llm' ? parameters : {});
      if (data.type === 'azure_openai' && data.api_version) {
        kept.api_version = data.api_version.trim();
      }

      const updateData: UpdateLLMConfigRequest = {
        display_name: data.display_name.trim(),
        llm_model: data.llm_model.trim(),
        type: data.type,
        model_type: data.model_type,
        parameters: Object.keys(kept).length > 0 ? kept : null,
        base_url: data.base_url?.trim() || null,
      };

      // Only include API key if it's been entered (since we don't show existing ones)
      if (data.api_key?.trim()) {
        updateData.api_key = data.api_key.trim();
      }

      await floConsoleService.llmInferenceService.updateLLMConfig(llmId, updateData);

      queryClient.invalidateQueries({ queryKey: getLLMConfigKey(appId || '', llmId || '') });
      queryClient.invalidateQueries({ queryKey: getLLMConfigsKey(appId || '') });
      setEditing(false);
      form.setValue('api_key', '');
      notifySuccess('Model updated successfully');
    } catch (error) {
      console.error('Error updating LLM inference config:', error);
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to update model');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!llmId || !config || !appId) return;
    try {
      await floConsoleService.llmInferenceService.deleteLLMConfig(llmId);
      queryClient.invalidateQueries({ queryKey: getLLMConfigKey(appId, llmId) });
      notifySuccess('Model deleted successfully');
      navigate(`/apps/${appId}/llm-repository`);
    } catch (error) {
      console.error('Error deleting LLM inference config:', error);
    }
  };

  return (
    <div className="h-full bg-transparent px-8 pt-8 pb-[200px]">
      <Breadcrumb className="mb-6">
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <button type="button" onClick={() => navigate('/apps')} className="hover:text-foreground cursor-pointer">
                Apps
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink asChild>
              <button
                type="button"
                onClick={() => navigate(`/apps/${appId}/llm-repository`)}
                className="hover:text-foreground cursor-pointer"
              >
                LLM Repository
              </button>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{config?.display_name || llmId}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <Spinner className="frost-text-muted h-8 w-8" />
        </div>
      ) : !config ? (
        <div className="frost-text-muted flex h-64 items-center justify-center">Model configuration not found</div>
      ) : (
        <div className="flex w-full flex-col gap-8 pb-5">
          <div className="flex items-center justify-between gap-4">
            <div className="flex min-w-0 flex-col gap-1">
              <p className="frost-text text-2xl leading-normal font-semibold">{formatAppName(config.display_name)}</p>
              <div className="frost-text-muted flex flex-wrap items-center gap-2 text-sm">
                <span>{getProviderConfig(config.type)?.name ?? config.type}</span>
                <span>·</span>
                <span className="font-mono">{config.llm_model}</span>
                <ModelTags tags={findModelPreset(config.type, config.llm_model)?.tags} />
              </div>
            </div>
            <div className="flex shrink-0 gap-4">
              {editing ? (
                <>
                  <Button onClick={form.handleSubmit(handleSave)} loading={saving}>
                    Save
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setEditing(false);
                      resetToSaved(config);
                    }}
                  >
                    Cancel
                  </Button>
                </>
              ) : (
                <Button variant="outline" onClick={() => setEditing(true)}>
                  Edit
                </Button>
              )}
              <Button variant="destructive" onClick={() => setShowDeleteConfirm(true)}>
                Delete
              </Button>
            </div>
          </div>

          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleSave)} className="flex w-full flex-col gap-6">
              <div className="frost-panel ring-frost-border flex w-full flex-col gap-6 rounded-lg border p-6 ring-1">
                <SectionTitle title="Model" />
                <div className={clsx('grid w-full gap-6 lg:grid-cols-2', !editing && 'opacity-80')}>
                  <FormField
                    control={form.control}
                    name="type"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Provider</FormLabel>
                        <ProviderSelect value={field.value} onChange={changeProvider} disabled={!editing} />
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="llm_model"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{providerConfig?.modelLabel ?? 'Model'}</FormLabel>
                        <ModelSelect provider={type} value={field.value} onChange={changeModel} disabled={!editing} />
                        {type === 'azure_openai' && editing && (
                          <Input
                            value={field.value}
                            onChange={(e) => changeModel(e.target.value)}
                            placeholder="Deployment name, e.g. gpt-5.4-nano"
                            aria-label="Deployment name"
                          />
                        )}
                        {editing && providerConfig?.modelHelp && (
                          <p className="frost-text-muted text-xs">{providerConfig.modelHelp}</p>
                        )}
                        {preset && <p className="frost-text-muted text-xs">{preset.description}</p>}
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="display_name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Display name</FormLabel>
                        <FormControl>
                          <Input disabled={!editing} placeholder="Display name" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="model_type"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Used for</FormLabel>
                        <Select
                          onValueChange={(val) => {
                            if (val) field.onChange(val);
                          }}
                          value={field.value}
                          disabled={!editing}
                        >
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="llm">Chat and voice (LLM)</SelectItem>
                            <SelectItem value="embedding">Embeddings</SelectItem>
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </div>

              <div className="frost-panel ring-frost-border flex w-full flex-col gap-6 rounded-lg border p-6 ring-1">
                <SectionTitle title="Connection" />
                <div className={clsx('grid w-full gap-6 lg:grid-cols-2', !editing && 'opacity-80')}>
                  {REQUIRES_API_KEY.includes(type) && (
                    <FormField
                      control={form.control}
                      name="api_key"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>API key</FormLabel>
                          <FormControl>
                            <Input
                              type="password"
                              autoComplete="off"
                              disabled={!editing}
                              placeholder={editing ? 'Leave blank to keep the current key' : '••••••••'}
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  )}

                  <FormField
                    control={form.control}
                    name="base_url"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{type === 'azure_openai' ? 'Endpoint' : 'Base URL'}</FormLabel>
                        <FormControl>
                          <Input
                            type="url"
                            disabled={!editing}
                            placeholder="Base URL for the API endpoint"
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  {type === 'azure_openai' && (
                    <FormField
                      control={form.control}
                      name="api_version"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>API version</FormLabel>
                          <FormControl>
                            <Input type="text" disabled={!editing} placeholder="2025-04-01-preview" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  )}
                </div>
              </div>

              {modelType === 'llm' && (
                <div className="frost-panel ring-frost-border flex w-full flex-col gap-6 rounded-lg border p-6 ring-1">
                  <SectionTitle
                    title="Settings"
                    description="Only the settings this model accepts are shown. An empty field uses the provider's default."
                  />
                  <div className={clsx(!editing && 'opacity-80')}>
                    <ModelParameters
                      provider={type}
                      modelId={llmModel}
                      values={parameters}
                      onChange={(key, value) => setParameters((prev) => ({ ...prev, [key]: value }))}
                      disabled={!editing}
                      droppedKeys={dropped}
                    />
                  </div>
                </div>
              )}
            </form>
          </Form>
        </div>
      )}

      <DeleteConfirmationDialog
        isOpen={showDeleteConfirm}
        title="Delete Model"
        message={`Are you sure you want to delete "${config?.display_name}"? This action cannot be undone.`}
        onConfirm={handleDelete}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </div>
  );
};

export default LLMInferenceConfigDetail;
