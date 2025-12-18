import floConsoleService from '@app/api';
import { Alert, AlertDescription, AlertTitle } from '@app/components/ui/alert';
import { Button } from '@app/components/ui/button';
import { Checkbox } from '@app/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Slider } from '@app/components/ui/slider';
import {
  cleanParameters,
  getDefaultBaseUrl,
  getProviderConfig,
  initializeParameters,
  ParameterConfig,
} from '@app/config/llm-providers';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { InferenceEngineType } from '@app/types/llm-inference-config';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
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

const MODEL_NAME_PLACEHOLDERS: Record<InferenceEngineType, string> = {
  openai: 'gpt-4, gpt-3.5-turbo',
  anthropic: 'claude-3-5-sonnet-20241022',
  gemini: 'gemini-pro, gemini-pro-vision',
  ollama: 'llama2, mistral',
  vllm: 'Model name',
  azure_openai: 'Model name',
  groq: 'Model name',
};

const BASE_URL_PLACEHOLDERS: Record<InferenceEngineType, string> = {
  ollama: 'http://localhost:11434',
  vllm: 'http://localhost:8000',
  azure_openai: 'https://your-resource.openai.azure.com',
  openai: 'https://api.openai.com/v1',
  anthropic: 'https://api.anthropic.com',
  gemini: 'https://generativelanguage.googleapis.com',
  groq: 'https://api.groq.com/openai/v1',
};

const createLLMInferenceSchema = z.object({
  displayName: z.string().min(1, 'Display name is required'),
  llmModel: z.string().min(1, 'LLM model name is required'),
  type: z.enum(['openai', 'anthropic', 'gemini', 'azure_openai', 'ollama', 'vllm', 'groq']),
  apiKey: z.string().optional(),
  baseUrl: z.string().optional(),
});

type CreateLLMInferenceInput = z.infer<typeof createLLMInferenceSchema>;

interface CreateLLMInferenceDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  onSuccess?: () => void;
}

const CreateLLMInferenceDialog: React.FC<CreateLLMInferenceDialogProps> = ({
  isOpen,
  onOpenChange,
  appId,
  onSuccess,
}) => {
  const navigate = useNavigate();
  const { notifySuccess, notifyError } = useNotifyStore();
  const [type, setType] = useState<InferenceEngineType>('openai');
  const [parameters, setParameters] = useState<Record<string, unknown>>({});
  const [creating, setCreating] = useState(false);
  const { selectedApp } = useDashboardStore();

  const form = useForm<CreateLLMInferenceInput>({
    resolver: zodResolver(createLLMInferenceSchema),
    defaultValues: {
      displayName: '',
      llmModel: '',
      type: 'openai',
      apiKey: '',
      baseUrl: getDefaultBaseUrl('openai'),
    },
  });

  // Initialize parameters when provider type changes
  const watchedType = form.watch('type');
  useEffect(() => {
    if (isOpen && watchedType) {
      const newType = watchedType as InferenceEngineType;
      setType(newType);
      const defaultParams = initializeParameters(newType);
      setParameters(defaultParams);

      // Set default base URL for the provider
      const defaultBaseUrl = getDefaultBaseUrl(newType);
      form.setValue('baseUrl', defaultBaseUrl);
    }
  }, [watchedType, isOpen, form]);

  // Reset form when dialog closes
  useEffect(() => {
    if (!isOpen) {
      const defaultType = 'openai';
      form.reset({
        displayName: '',
        llmModel: '',
        type: defaultType,
        apiKey: '',
        baseUrl: getDefaultBaseUrl(defaultType),
      });
      setType(defaultType);
      setParameters(initializeParameters(defaultType));
    }
  }, [isOpen, form]);

  const requiresApiKey = (engineType: InferenceEngineType) => {
    return ['openai', 'anthropic', 'gemini', 'azure_openai', 'groq'].includes(engineType);
  };

  const supportsBaseUrl = (engineType: InferenceEngineType) => {
    return ['ollama', 'vllm', 'azure_openai', 'openai', 'anthropic', 'gemini', 'groq'].includes(engineType);
  };

  const setParameter = (key: string, value: unknown) => {
    setParameters((prev) => ({ ...prev, [key]: value }));
  };

  const onSubmit = async (data: CreateLLMInferenceInput) => {
    if (!appId) {
      notifyError('LLM inference config service not available');
      return;
    }

    if (!data.displayName.trim() || !data.llmModel.trim()) {
      notifyError('Please fill in all required fields');
      return;
    }

    setCreating(true);
    try {
      const cleanedParams = cleanParameters(parameters);

      const response = await floConsoleService.llmInferenceService.createLLMConfig({
        display_name: data.displayName.trim(),
        llm_model: data.llmModel.trim(),
        api_key: data.apiKey?.trim() || undefined,
        type: data.type,
        base_url: data.baseUrl?.trim() || undefined,
        parameters: Object.keys(cleanedParams).length > 0 ? cleanedParams : undefined,
      });

      const responseData = response.data?.data;
      if (responseData?.id) {
        notifySuccess('Model added to repository successfully');

        if (onSuccess) {
          onSuccess();
        }

        onOpenChange(false);

        navigate(`/apps/${appId}/model-repository/${responseData.id}`);
      } else {
        notifySuccess('Model added to repository successfully');

        if (onSuccess) {
          onSuccess();
        }

        onOpenChange(false);
      }
    } catch (error) {
      console.error('Error creating LLM inference config:', error);
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to add model to repository');
    } finally {
      setCreating(false);
    }
  };

  const renderParameterField = (paramKey: string, paramConfig: ParameterConfig) => {
    if (paramConfig.type === 'number') {
      const currentValue = parameters[paramKey] ?? paramConfig.default ?? paramConfig.min ?? 0;
      return (
        <div className="space-y-2">
          <Input
            type="number"
            value={parameters[paramKey] ?? ''}
            onChange={(e) => {
              const value = e.target.value === '' ? undefined : parseFloat(e.target.value);
              setParameter(paramKey, value);
            }}
            min={paramConfig.min}
            max={paramConfig.max}
            step={paramConfig.step}
            placeholder={paramConfig.placeholder}
          />
          {paramConfig.min !== undefined && paramConfig.max !== undefined && (
            <Slider
              value={[currentValue]}
              onValueChange={(values: number[]) => {
                setParameter(paramKey, values[0]);
              }}
              min={paramConfig.min}
              max={paramConfig.max}
              step={paramConfig.step}
              className="w-full"
            />
          )}
        </div>
      );
    }

    if (paramConfig.type === 'boolean') {
      return (
        <div className="flex items-center gap-3">
          <Checkbox
            checked={parameters[paramKey] ?? paramConfig.default ?? false}
            onCheckedChange={(checked) => setParameter(paramKey, checked)}
          />
          <label className="text-sm text-gray-700">Enable</label>
        </div>
      );
    }

    if (paramConfig.type === 'string' && !paramConfig.options) {
      return (
        <Input
          type="text"
          value={parameters[paramKey] ?? ''}
          onChange={(e) => {
            const value = e.target.value || undefined;
            setParameter(paramKey, value);
          }}
          placeholder={paramConfig.placeholder}
        />
      );
    }

    if (paramConfig.type === 'select' && paramConfig.options) {
      const currentValue = parameters[paramKey];
      return (
        <Select
          value={currentValue !== undefined && currentValue !== null ? String(currentValue) : undefined}
          onValueChange={(value) => setParameter(paramKey, value || undefined)}
        >
          <SelectTrigger>
            <SelectValue placeholder="Select an option" />
          </SelectTrigger>
          <SelectContent>
            {paramConfig.options.map((option) => (
              <SelectItem key={String(option.value)} value={String(option.value)}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    }

    return null;
  };

  const providerConfig = getProviderConfig(type);

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto lg:max-w-5xl">
        <DialogHeader>
          <DialogTitle>Add LLM to Repository</DialogTitle>
          <DialogDescription>Add a new LLM to your repository for {selectedApp?.app_name}</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <div className="grid grid-cols-2 gap-6">
              <FormField
                control={form.control}
                name="displayName"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Display Name<span className="text-red-500">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="My GPT-4 Configuration" {...field} />
                    </FormControl>
                    <FormDescription>A friendly name for this AI model</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Inference Engine Type<span className="text-red-500">*</span>
                    </FormLabel>
                    <Select
                      onValueChange={(value) => {
                        field.onChange(value);
                        const newType = value as InferenceEngineType;
                        setType(newType);
                        setParameters(initializeParameters(newType));

                        // Set default base URL for the provider
                        const defaultBaseUrl = getDefaultBaseUrl(newType);
                        form.setValue('baseUrl', defaultBaseUrl);
                      }}
                      value={field.value}
                    >
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
                    <FormDescription>Choose the type of LLM inference engine</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <div className="grid grid-cols-2 gap-6">
              <FormField
                control={form.control}
                name="llmModel"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      LLM Model Name<span className="text-red-500">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input placeholder={MODEL_NAME_PLACEHOLDERS[type]} {...field} />
                    </FormControl>
                    <FormDescription>
                      Specify the exact model name (e.g., gpt-4, claude-3-5-sonnet-20241022, gemini-pro)
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {requiresApiKey(type) && (
                <FormField
                  control={form.control}
                  name="apiKey"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>API Key{requiresApiKey(type) && <span className="text-red-500">*</span>}</FormLabel>
                      <FormControl>
                        <Input type="password" placeholder="Your API key" {...field} />
                      </FormControl>
                      <FormDescription>
                        API key for authenticating with the{' '}
                        {INFERENCE_ENGINE_TYPES.find((t) => t.value === type)?.label} service
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              {supportsBaseUrl(type) && (
                <FormField
                  control={form.control}
                  name="baseUrl"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Base URL{(type === 'ollama' || type === 'vllm') && <span className="text-red-500">*</span>}
                      </FormLabel>
                      <FormControl>
                        <Input type="url" placeholder={BASE_URL_PLACEHOLDERS[type]} {...field} />
                      </FormControl>
                      <FormDescription>
                        {type === 'ollama' || type === 'vllm'
                          ? 'Required base URL for your local inference server'
                          : 'Optional custom base URL for the API endpoint'}
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
            </div>

            {/* Provider-specific Parameters Section */}
            {providerConfig && Object.keys(providerConfig.parameters).length > 0 && (
              <div className="space-y-4 rounded-lg border border-gray-200 bg-white p-6">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">Model Parameters</h3>
                  <p className="text-sm text-gray-500">Configure provider-specific parameters for this model</p>
                </div>
                <div className="grid grid-cols-4 gap-6">
                  {Object.entries(providerConfig.parameters).map(
                    ([paramKey, paramConfig]: [string, ParameterConfig]) => (
                      <div key={paramKey}>
                        <label className="block pb-2 text-sm font-medium text-gray-700">
                          {paramKey.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
                        </label>
                        {renderParameterField(paramKey, paramConfig)}
                        {paramConfig.description && (
                          <p className="mt-1 text-xs text-gray-500">{paramConfig.description}</p>
                        )}
                      </div>
                    )
                  )}
                </div>
              </div>
            )}

            <Alert variant="info">
              <AlertTitle>Security Note</AlertTitle>
              <AlertDescription>
                API keys are stored securely and are never returned in API responses. Only store API keys for models
                that require authentication.
              </AlertDescription>
            </Alert>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={creating || form.formState.isSubmitting}>
                Add Model
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateLLMInferenceDialog;
