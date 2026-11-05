import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import DetailActions from '@app/components/DetailActions';
import MobileBackButton from '@app/components/MobileBackButton';
import PageTitle from '@app/components/PageTitle';
import { ModelParameters } from '@app/components/llm/ModelParameters';
import { ModelSelect, ModelTags } from '@app/components/llm/ModelSelect';
import { ProviderSelect } from '@app/components/llm/ProviderSelect';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Spinner } from '@app/components/ui/spinner';
import { filterParameters, findModelPreset, getDefaultModelId } from '@app/config/llm-models';
import { getDefaultBaseUrl, getProviderConfig } from '@app/config/llm-providers';
import { useDeleteLLMConfig, useGetLLMConfig, useUpdateLLMConfig } from '@app/hooks';
import { formatAppName } from '@app/utils/string-formatting';
import { InferenceEngineType, LLMInferenceConfig, UpdateLLMConfigRequest } from '@app/types/llm-inference-config';
import { zodResolver } from '@hookform/resolvers/zod';
import clsx from 'clsx';
import React, { useCallback, useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate, useParams } from 'react-router';
import { z } from 'zod';
import PageBreadcrumb from '@app/components/PageBreadcrumb';

const REQUIRES_API_KEY: InferenceEngineType[] = ['openai', 'anthropic', 'gemini', 'azure_openai', 'groq'];

const modelFormSchema = z
  .object({
    display_name: z.string().min(1, 'Display name is required'),
    llm_model: z.string().min(1, 'Choose a model'),
    type: z.enum(['openai', 'anthropic', 'gemini', 'azure_openai', 'ollama', 'vllm', 'groq', 'bedrock']),
    api_key: z.string().optional(),
    model_type: z.enum(['llm', 'embedding']),
    base_url: z.string().optional(),
    api_version: z.string().optional(),
    aws_access_key_id: z.string().optional(),
    aws_region: z.string().optional(),
  })
  .superRefine((data, ctx) => {
    if (data.type === 'azure_openai' && !data.api_version?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['api_version'],
        message: 'API version is required for Azure OpenAI',
      });
    }
    if (data.type === 'bedrock' && !data.aws_region?.trim()) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['aws_region'], message: 'Region is required' });
    }
  });

type ModelForm = z.infer<typeof modelFormSchema>;

/**
 * Build the complete set of form values from a saved config.
 * Shared by the initial load and the edit-cancel revert so neither can omit a
 * field: `form.reset` replaces every value, so a partial payload would silently
 * blank out whatever it left out (e.g. the Azure-only `api_version`).
 */
const buildFormValues = (config: LLMInferenceConfig): ModelForm => ({
  display_name: config.display_name,
  llm_model: config.llm_model,
  type: config.type,
  model_type: (config.model_type as 'llm' | 'embedding') || 'llm',
  api_key: '', // API key is never returned for security
  base_url: config.base_url || '',
  api_version: (config.parameters?.api_version as string) || '',
  aws_access_key_id: (config.parameters?.aws_access_key_id as string) || '',
  aws_region: (config.parameters?.aws_region as string) || '',
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

const ModelDetail: React.FC = () => {
  const { app: appId, modelId } = useParams<{ app: string; modelId: string }>();
  const navigate = useNavigate();
  const updateLLMConfig = useUpdateLLMConfig(appId);
  const deleteLLMConfig = useDeleteLLMConfig(appId);

  const { data: config, isLoading } = useGetLLMConfig(appId, modelId);

  const [editing, setEditing] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [parameters, setParameters] = useState<Record<string, unknown>>({});

  const form = useForm<ModelForm>({
    resolver: zodResolver(modelFormSchema),
    defaultValues: {
      display_name: '',
      llm_model: '',
      type: 'openai',
      model_type: 'llm',
      api_key: '',
      base_url: '',
      api_version: '',
      aws_access_key_id: '',
      aws_region: '',
    },
    mode: 'onChange',
  });

  const resetToSaved = useCallback(
    (saved: LLMInferenceConfig) => {
      form.reset(buildFormValues(saved));
      setParameters(savedParameters(saved));
    },
    [form]
  );

  useEffect(() => {
    if (config) resetToSaved(config);
  }, [config, resetToSaved]);

  const type = form.watch('type');
  const llmModel = form.watch('llm_model');
  const modelType = form.watch('model_type');
  const providerConfig = getProviderConfig(type);
  const preset = findModelPreset(type, llmModel);
  // Settings saved on this config that the current model rejects; the next save drops them.
  const dropped = config ? filterParameters(type, llmModel, config.parameters).dropped : [];

  const changeProvider = (newType: InferenceEngineType) => {
    if (newType === type) return;
    // The old provider's model means nothing to the new one: pick a sensible one (chat models only)
    const newModel = modelType === 'llm' ? getDefaultModelId(newType) : '';
    form.setValue('type', newType, { shouldValidate: true });
    form.setValue('llm_model', newModel, { shouldValidate: true });
    form.setValue('base_url', getDefaultBaseUrl(newType));
    if (newType === 'bedrock' && !form.getValues('aws_region')) form.setValue('aws_region', 'us-east-1');
    setParameters((prev) => filterParameters(newType, newModel, prev).kept);
  };

  const changeModel = (modelId: string) => {
    form.setValue('llm_model', modelId, { shouldValidate: true });
  };

  const handleSave = (data: ModelForm) => {
    if (!modelId || !config) return;

    // The access key ID and secret are one credential: save both, keep the saved pair
    // untouched, or clear both. The secret is never returned, so a blank secret only
    // means "keep" when the ID is the one already saved on this Bedrock config.
    const keyId = data.type === 'bedrock' ? data.aws_access_key_id?.trim() || '' : '';
    const secret = data.api_key?.trim() || '';
    const savedKeyId = config.type === 'bedrock' ? (config.parameters?.aws_access_key_id as string) || '' : '';
    if (data.type === 'bedrock') {
      if (secret && !keyId) {
        form.setError('aws_access_key_id', { message: 'Enter the access key ID for this secret' });
        return;
      }
      if (!secret && keyId && keyId !== savedKeyId) {
        form.setError('api_key', { message: 'Enter the secret access key for this access key ID' });
        return;
      }
    }
    // Leaving Bedrock: the stored key is an AWS secret, never a valid key for the new provider
    const leavingBedrock = config.type === 'bedrock' && data.type !== 'bedrock';
    if (leavingBedrock && !secret && REQUIRES_API_KEY.includes(data.type)) {
      form.setError('api_key', { message: `Enter the API key for ${getProviderConfig(data.type)?.name ?? data.type}` });
      return;
    }

    // Only what this model accepts goes out, so a stale or unsupported setting cannot fail requests
    const { kept } = filterParameters(data.type, data.llm_model, data.model_type === 'llm' ? parameters : {});
    if (data.type === 'azure_openai' && data.api_version) {
      kept.api_version = data.api_version.trim();
    }
    if (data.type === 'bedrock') {
      kept.aws_region = data.aws_region?.trim();
      if (keyId) kept.aws_access_key_id = keyId;
    }

    const updateData: UpdateLLMConfigRequest = {
      display_name: data.display_name.trim(),
      llm_model: data.llm_model.trim(),
      type: data.type,
      model_type: data.model_type,
      parameters: Object.keys(kept).length > 0 ? kept : null,
      base_url: (data.type !== 'bedrock' && data.base_url?.trim()) || null,
    };

    // Only include API key if it's been entered (since we don't show existing ones)
    if (secret) {
      updateData.api_key = secret;
    } else if ((data.type === 'bedrock' && !keyId) || leavingBedrock) {
      // Ambient AWS credentials, or a keyless provider after Bedrock: clear the stored secret
      updateData.api_key = null;
    }

    updateLLMConfig.mutate(
      { configId: modelId, data: updateData },
      {
        onSuccess: () => {
          setEditing(false);
          form.setValue('api_key', '');
        },
      }
    );
  };

  const handleDelete = () => {
    if (!modelId || !config || !appId) return;
    deleteLLMConfig.mutate(modelId, { onSuccess: () => navigate(`/apps/${appId}/model-hub`) });
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-transparent px-4 pt-4 pb-4 sm:px-8 sm:pt-8 sm:pb-8 lg:overflow-hidden">
      <PageBreadcrumb
        className="shrink-0"
        items={[
          { label: 'Model Hub', to: `/apps/${appId}/model-hub` },
          { label: config?.display_name || modelId, loading: isLoading },
        ]}
      />

      {isLoading ? (
        <div className="flex w-full flex-col gap-8">
          <div className="flex min-w-0 items-center gap-2">
            <MobileBackButton to={`/apps/${appId}/model-hub`} label="Back to Model Hub" />
            <PageTitle loading />
          </div>
          <div className="flex h-64 items-center justify-center">
            <Spinner className="frost-text-muted h-8 w-8" />
          </div>
        </div>
      ) : !config ? (
        <div className="frost-text-muted flex h-64 items-center justify-center">Model configuration not found</div>
      ) : (
        <div className="flex w-full flex-col gap-8 lg:min-h-0 lg:flex-1">
          <div className="flex shrink-0 items-start justify-between gap-3">
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <div className="flex min-w-0 items-center gap-2">
                <MobileBackButton to={`/apps/${appId}/model-hub`} label="Back to Model Hub" />
                <PageTitle>{formatAppName(config.display_name)}</PageTitle>
              </div>
              <div className="frost-text-muted flex flex-wrap items-center gap-2 text-sm">
                <span>{getProviderConfig(config.type)?.name ?? config.type}</span>
                <span>·</span>
                <span className="font-mono">{config.llm_model}</span>
                <ModelTags tags={findModelPreset(config.type, config.llm_model)?.tags} />
              </div>
            </div>
            <DetailActions
              editing={editing}
              onEdit={() => setEditing(true)}
              onDelete={() => setShowDeleteConfirm(true)}
              onSave={form.handleSubmit(handleSave)}
              onCancel={() => {
                setEditing(false);
                resetToSaved(config);
              }}
              saving={updateLLMConfig.isPending}
            />
          </div>

          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleSave)} className="flex w-full flex-col lg:min-h-0 lg:flex-1">
              <div className="flex w-full flex-col gap-6 lg:min-h-0 lg:flex-1 lg:flex-row">
                <div className="flex min-w-0 flex-1 flex-col gap-6 lg:min-h-0 lg:overflow-y-auto">
                  <div className="frost-panel ring-frost-border flex w-full shrink-0 flex-col gap-6 rounded-lg border p-6 ring-1">
                    <SectionTitle title="Model" />
                    <div className={clsx('grid w-full gap-6 lg:grid-cols-2', !editing && 'opacity-80')}>
                      <FormField
                        control={form.control}
                        name="display_name"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Name</FormLabel>
                            <FormControl>
                              <Input disabled={!editing} placeholder="Name" {...field} />
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
                            <FormLabel>Type</FormLabel>
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
                            <ModelSelect
                              provider={type}
                              value={field.value}
                              onChange={changeModel}
                              disabled={!editing}
                            />
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
                    </div>
                  </div>

                  <div className="frost-panel ring-frost-border flex w-full shrink-0 flex-col gap-6 rounded-lg border p-6 ring-1">
                    <SectionTitle title="Connection" />
                    <div className={clsx('grid w-full gap-6 lg:grid-cols-2', !editing && 'opacity-80')}>
                      {type !== 'bedrock' && (
                        <FormField
                          control={form.control}
                          name="base_url"
                          render={({ field }) => (
                            <FormItem className="lg:col-span-2">
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
                      )}

                      {type === 'bedrock' && (
                        <>
                          <FormField
                            control={form.control}
                            name="aws_region"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel>Region</FormLabel>
                                <FormControl>
                                  <Input disabled={!editing} placeholder="us-east-1" {...field} />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                          <FormField
                            control={form.control}
                            name="aws_access_key_id"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel>Access key ID</FormLabel>
                                <FormControl>
                                  <Input
                                    disabled={!editing}
                                    autoComplete="off"
                                    placeholder="Empty uses the server's AWS credentials"
                                    {...field}
                                  />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </>
                      )}

                      {(REQUIRES_API_KEY.includes(type) || type === 'bedrock') && (
                        <FormField
                          control={form.control}
                          name="api_key"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>{type === 'bedrock' ? 'Secret access key' : 'API key'}</FormLabel>
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
                </div>

                {modelType === 'llm' && (
                  <div className="frost-panel ring-frost-border flex w-full flex-col gap-6 rounded-lg border p-6 ring-1 lg:min-h-0 lg:w-[420px] lg:shrink-0">
                    <SectionTitle
                      title="Settings"
                      description="Only the settings this model accepts are shown. An empty field uses the provider's default."
                    />
                    <div className={clsx('lg:min-h-0 lg:flex-1 lg:overflow-y-auto', !editing && 'opacity-80')}>
                      <ModelParameters
                        provider={type}
                        modelId={llmModel}
                        values={parameters}
                        onChange={(key, value) => setParameters((prev) => ({ ...prev, [key]: value }))}
                        disabled={!editing}
                        droppedKeys={dropped}
                        compact
                      />
                    </div>
                  </div>
                )}
              </div>
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

export default ModelDetail;
