import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@app/components/ui/breadcrumb';
import { Button } from '@app/components/ui/button';
import { Checkbox } from '@app/components/ui/checkbox';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Slider } from '@app/components/ui/slider';
import { cleanParameters, getProviderConfig, mergeParameters, ParameterConfig } from '@app/config/llm-providers';
import { useGetLLMConfig } from '@app/hooks';
import { getLLMConfigKey, getLLMConfigsKey } from '@app/hooks/data/query-keys';
import { useNotifyStore } from '@app/store';
import { InferenceEngineType } from '@app/types/llm-inference-config';
import { zodResolver } from '@hookform/resolvers/zod';
import { useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate, useParams } from 'react-router';
import { z } from 'zod';

const INFERENCE_ENGINE_TYPES = [
  { value: 'openai' as InferenceEngineType, label: 'OpenAI GPT' },
  { value: 'anthropic' as InferenceEngineType, label: 'Anthropic Claude' },
  { value: 'gemini' as InferenceEngineType, label: 'Google Gemini' },
  { value: 'azure_openai' as InferenceEngineType, label: 'Azure OpenAI' },
  { value: 'ollama' as InferenceEngineType, label: 'Ollama (Local)' },
  { value: 'vllm' as InferenceEngineType, label: 'vLLM' },
  { value: 'groq' as InferenceEngineType, label: 'Groq' },
];

const llmConfigFormSchema = z.object({
  display_name: z.string().min(1, 'Display name is required'),
  llm_model: z.string().min(1, 'LLM model is required'),
  type: z.enum(['openai', 'anthropic', 'gemini', 'azure_openai', 'ollama', 'vllm', 'groq']),
  api_key: z.string().optional(),
  base_url: z.string().optional(),
  parameters: z.record(z.any()).optional(),
});

type LLMConfigForm = z.infer<typeof llmConfigFormSchema>;

const LLMInferenceConfigDetail: React.FC = () => {
  const { app: appId, llmId } = useParams<{ app: string; llmId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  // Fetch LLM config
  const { data: config } = useGetLLMConfig(appId, llmId);

  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [parameters, setParameters] = useState<Record<string, any>>({});

  const form = useForm<LLMConfigForm>({
    resolver: zodResolver(llmConfigFormSchema),
    defaultValues: {
      display_name: '',
      llm_model: '',
      type: 'openai',
      api_key: '',
      base_url: '',
      parameters: {},
    },
    mode: 'onChange',
  });

  // Update form fields when config loads
  useEffect(() => {
    if (config) {
      // Merge saved parameters with defaults
      const mergedParams = mergeParameters(config.type, config.parameters);
      setParameters(mergedParams);
      form.reset({
        display_name: config.display_name,
        llm_model: config.llm_model,
        type: config.type,
        api_key: '', // API key is never returned for security
        base_url: config.base_url || '',
        parameters: mergedParams,
      });
    }
  }, [config, form]);

  // Update parameters when provider type changes in edit mode
  const watchedType = form.watch('type');
  useEffect(() => {
    if (editing && config) {
      const mergedParams = mergeParameters(watchedType, watchedType === config.type ? config.parameters : null);
      setParameters(mergedParams);
      form.setValue('parameters', mergedParams);
    }
  }, [watchedType, editing, config, form]);

  // Sync parameters state with form when parameters change
  useEffect(() => {
    if (editing) {
      form.setValue('parameters', parameters);
    }
  }, [parameters, editing, form]);

  const handleSave = async (data: LLMConfigForm) => {
    if (!llmId || !config) return;

    setSaving(true);
    try {
      // Clean parameters before sending (remove undefined/null/empty values)
      const cleanedParams = cleanParameters(parameters);

      // Only include fields that have changed or are explicitly set
      const updateData: any = {
        display_name: data.display_name.trim(),
        llm_model: data.llm_model.trim(),
        type: data.type,
        parameters: Object.keys(cleanedParams).length > 0 ? cleanedParams : null,
      };

      // Only include base_url if it's supported by the engine type
      if (supportsBaseUrl(data.type)) {
        updateData.base_url = data.base_url?.trim() || null;
      }

      // Only include API key if it's been entered (since we don't show existing ones)
      if (data.api_key?.trim()) {
        updateData.api_key = data.api_key.trim();
      }

      await floConsoleService.llmInferenceService.updateLLMConfig(llmId, updateData);

      // Invalidate queries to refetch updated data
      queryClient.invalidateQueries({ queryKey: getLLMConfigKey(appId || '', llmId || '') });
      queryClient.invalidateQueries({ queryKey: getLLMConfigsKey(appId || '') });
      setEditing(false);
      form.setValue('api_key', ''); // Clear API key after saving
      notifySuccess('Model updated successfully');
    } catch (error) {
      console.error('Error updating LLM inference config:', error);

      let errorMessage = 'Failed to update model';
      if (error && typeof error === 'object' && 'response' in error) {
        const response = (error as any).response;
        if (response?.data?.error) {
          errorMessage = response.data.error;
        } else if (response?.data?.message) {
          errorMessage = response.data.message;
        }
      }

      notifyError(errorMessage);
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
      navigate(`/apps/${appId}/llm-inference`);
    } catch (error) {
      console.error('Error deleting LLM inference config:', error);
    }
  };

  const requiresApiKey = (engineType: InferenceEngineType) => {
    return ['openai', 'anthropic', 'gemini', 'azure_openai', 'groq'].includes(engineType);
  };

  const supportsBaseUrl = (engineType: InferenceEngineType) => {
    return ['ollama', 'vllm', 'azure_openai'].includes(engineType);
  };

  return (
    <div className="h-full bg-white px-8 pt-8 pb-[200px]">
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

      <div className="flex w-full flex-col gap-10 pb-5">
        <div className="flex items-center justify-between">
          <p className="text-2xl leading-normal font-semibold text-black">{config?.display_name}</p>
          <div className="flex gap-4">
            {editing ? (
              <>
                <Button onClick={form.handleSubmit(handleSave)} loading={saving}>
                  Save
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setEditing(false);
                    // Revert changes by resetting form to config data
                    if (config) {
                      const mergedParams = mergeParameters(config.type, config.parameters);
                      form.reset({
                        display_name: config.display_name,
                        llm_model: config.llm_model,
                        type: config.type,
                        api_key: '',
                        base_url: config.base_url || '',
                        parameters: mergedParams,
                      });
                      setParameters(mergedParams);
                    }
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

        <div className="flex w-full flex-col gap-6">
          <div className="flex w-full flex-col gap-6 rounded-lg border border-gray-200 bg-white p-6">
            <h3 className="text-lg font-semibold text-gray-900">Model Details</h3>
            <Form {...form}>
              <form onSubmit={form.handleSubmit(handleSave)} className="flex w-full flex-col gap-6">
                <div className={clsx('grid w-full gap-6 lg:grid-cols-2', !editing && 'pointer-events-none opacity-80')}>
                  <FormField
                    control={form.control}
                    name="display_name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Display Name</FormLabel>
                        <FormControl>
                          <Input disabled={!editing} placeholder="Display name" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="llm_model"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>LLM Model</FormLabel>
                        <FormControl>
                          <Input disabled={!editing} placeholder="Model name" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="type"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Inference Engine Type</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value} disabled={!editing}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Select engine type" />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {INFERENCE_ENGINE_TYPES.map((engineType) => (
                              <SelectItem key={engineType.value} value={engineType.value}>
                                {engineType.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  {requiresApiKey(form.watch('type')) && (
                    <FormField
                      control={form.control}
                      name="api_key"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>API Key</FormLabel>
                          <FormControl>
                            <Input
                              type="password"
                              disabled={!editing}
                              placeholder="Enter new API key (leave blank to keep current)"
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                          <p className="text-xs text-gray-500">
                            Leave blank to keep the current API key. Enter a new key to update it.
                          </p>
                        </FormItem>
                      )}
                    />
                  )}

                  {supportsBaseUrl(form.watch('type')) && (
                    <FormField
                      control={form.control}
                      name="base_url"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Base URL</FormLabel>
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
                </div>
              </form>
            </Form>
          </div>

          {/* Model Parameters Section */}
          {(() => {
            const currentType = form.watch('type') || config?.type;
            const providerConfig = currentType ? getProviderConfig(currentType) : null;
            if (!providerConfig || !config || Object.keys(providerConfig.parameters).length === 0) {
              return null;
            }

            return (
              <div className="flex w-full flex-col gap-6 rounded-lg border border-gray-200 bg-white p-6">
                <h3 className="text-lg font-semibold text-gray-900">Model Parameters</h3>
                <Form {...form}>
                  <div className={clsx('grid w-full grid-cols-4 gap-6', !editing && 'pointer-events-none opacity-80')}>
                    {Object.entries(providerConfig.parameters).map(
                      ([paramKey, paramConfig]: [string, ParameterConfig]) => (
                        <FormField
                          key={paramKey}
                          control={form.control}
                          name={`parameters.${paramKey}`}
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>
                                {paramKey.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
                              </FormLabel>
                              <FormControl>
                                {paramConfig.type === 'number' ? (
                                  <div className="space-y-2">
                                    <Input
                                      type="number"
                                      value={parameters[paramKey] ?? ''}
                                      onChange={(e) => {
                                        const value = e.target.value === '' ? undefined : parseFloat(e.target.value);
                                        setParameters((prev) => ({ ...prev, [paramKey]: value }));
                                        field.onChange(value);
                                      }}
                                      min={paramConfig.min}
                                      max={paramConfig.max}
                                      step={paramConfig.step}
                                      placeholder={paramConfig.placeholder}
                                      disabled={!editing}
                                    />
                                    {paramConfig.min !== undefined && paramConfig.max !== undefined && (
                                      <Slider
                                        value={[parameters[paramKey] ?? paramConfig.default ?? paramConfig.min]}
                                        onValueChange={(values) => {
                                          const value = values[0];
                                          setParameters((prev) => ({ ...prev, [paramKey]: value }));
                                          field.onChange(value);
                                        }}
                                        min={paramConfig.min}
                                        max={paramConfig.max}
                                        step={paramConfig.step}
                                        disabled={!editing}
                                      />
                                    )}
                                  </div>
                                ) : paramConfig.type === 'boolean' ? (
                                  <div className="flex items-center space-x-2">
                                    <Checkbox
                                      checked={parameters[paramKey] ?? paramConfig.default ?? false}
                                      onCheckedChange={(checked) => {
                                        setParameters((prev) => ({ ...prev, [paramKey]: checked }));
                                        field.onChange(checked);
                                      }}
                                      disabled={!editing}
                                    />
                                    <label className="text-sm leading-none font-medium peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                                      Enable
                                    </label>
                                  </div>
                                ) : paramConfig.type === 'select' && paramConfig.options ? (
                                  <Select
                                    value={parameters[paramKey] ? String(parameters[paramKey]) : ''}
                                    onValueChange={(value) => {
                                      const val = value || undefined;
                                      setParameters((prev) => ({ ...prev, [paramKey]: val }));
                                      field.onChange(val);
                                    }}
                                    disabled={!editing}
                                  >
                                    <FormControl>
                                      <SelectTrigger>
                                        <SelectValue placeholder="-- Select --" />
                                      </SelectTrigger>
                                    </FormControl>
                                    <SelectContent>
                                      {paramConfig.options.map((option) => (
                                        <SelectItem key={String(option.value)} value={String(option.value)}>
                                          {option.label}
                                        </SelectItem>
                                      ))}
                                    </SelectContent>
                                  </Select>
                                ) : (
                                  <Input
                                    type="text"
                                    value={parameters[paramKey] ?? ''}
                                    onChange={(e) => {
                                      const value = e.target.value || undefined;
                                      setParameters((prev) => ({ ...prev, [paramKey]: value }));
                                      field.onChange(value);
                                    }}
                                    placeholder={paramConfig.placeholder}
                                    disabled={!editing}
                                  />
                                )}
                              </FormControl>
                              {paramConfig.description && (
                                <p className="text-xs text-gray-500">{paramConfig.description}</p>
                              )}
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      )
                    )}
                  </div>
                </Form>
              </div>
            );
          })()}
        </div>

        {/* Delete Confirmation Dialog */}
        <DeleteConfirmationDialog
          isOpen={showDeleteConfirm}
          title="Delete Model"
          message={`Are you sure you want to delete "${config?.display_name}"? This action cannot be undone.`}
          onConfirm={handleDelete}
          onCancel={() => setShowDeleteConfirm(false)}
        />
      </div>
    </div>
  );
};

export default LLMInferenceConfigDetail;
