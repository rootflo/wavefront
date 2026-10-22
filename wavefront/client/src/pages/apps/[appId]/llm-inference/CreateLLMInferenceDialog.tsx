import floConsoleService from '@app/api';
import { ModelParameters } from '@app/components/llm/ModelParameters';
import { ModelSelect } from '@app/components/llm/ModelSelect';
import { ProviderSelect } from '@app/components/llm/ProviderSelect';
import { Alert, AlertDescription } from '@app/components/ui/alert';
import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { filterParameters, findModelPreset, getDefaultModelId } from '@app/config/llm-models';
import { getDefaultBaseUrl, getProviderConfig } from '@app/config/llm-providers';
import { extractErrorMessage } from '@app/lib/utils';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { InferenceEngineType } from '@app/types/llm-inference-config';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { z } from 'zod';

const BASE_URL_PLACEHOLDERS: Record<InferenceEngineType, string> = {
  ollama: 'http://localhost:11434',
  vllm: 'http://localhost:8000',
  azure_openai: 'https://your-resource.openai.azure.com',
  openai: 'https://api.openai.com/v1',
  anthropic: 'https://api.anthropic.com',
  gemini: 'https://generativelanguage.googleapis.com',
  groq: 'https://api.groq.com/openai/v1',
  bedrock: '',
};

const REQUIRES_API_KEY: InferenceEngineType[] = ['openai', 'anthropic', 'gemini', 'azure_openai', 'groq'];

const createLLMInferenceSchema = z
  .object({
    displayName: z.string().min(1, 'Display name is required'),
    llmModel: z.string().min(1, 'Choose a model'),
    type: z.enum(['openai', 'anthropic', 'gemini', 'azure_openai', 'ollama', 'vllm', 'groq', 'bedrock']),
    modelType: z.enum(['llm', 'embedding']),
    apiKey: z.string().optional(),
    baseUrl: z.string().optional(),
    apiVersion: z.string().optional(),
    awsAccessKeyId: z.string().optional(),
    awsRegion: z.string().optional(),
  })
  .superRefine((data, ctx) => {
    if (data.type === 'azure_openai' && !data.apiVersion?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['apiVersion'],
        message: 'API version is required for Azure OpenAI',
      });
    }
    if ((data.type === 'ollama' || data.type === 'vllm') && !data.baseUrl?.trim()) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['baseUrl'], message: 'Base URL is required' });
    }
    if (data.type === 'bedrock') {
      if (!data.awsRegion?.trim()) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['awsRegion'], message: 'Region is required' });
      }
      const hasKeyId = !!data.awsAccessKeyId?.trim();
      const hasSecret = !!data.apiKey?.trim();
      if (hasKeyId !== hasSecret) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: [hasKeyId ? 'apiKey' : 'awsAccessKeyId'],
          message: "Enter both keys, or neither to use the server's AWS credentials",
        });
      }
    }
  });

type CreateLLMInferenceInput = z.infer<typeof createLLMInferenceSchema>;

const DEFAULT_TYPE: InferenceEngineType = 'openai';

const emptyForm = (type: InferenceEngineType): CreateLLMInferenceInput => ({
  displayName: '',
  llmModel: '',
  type,
  modelType: 'llm',
  apiKey: '',
  baseUrl: getDefaultBaseUrl(type),
  apiVersion: type === 'azure_openai' ? '2025-04-01-preview' : '',
  awsAccessKeyId: '',
  awsRegion: type === 'bedrock' ? 'us-east-1' : '',
});

interface CreateLLMInferenceDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  onSuccess?: () => void;
}

const SectionTitle: React.FC<{ title: string; description?: string }> = ({ title, description }) => (
  <div>
    <h3 className="frost-text text-base font-semibold">{title}</h3>
    {description && <p className="frost-text-muted text-sm">{description}</p>}
  </div>
);

const CreateLLMInferenceDialog: React.FC<CreateLLMInferenceDialogProps> = ({
  isOpen,
  onOpenChange,
  appId,
  onSuccess,
}) => {
  const navigate = useNavigate();
  const { notifySuccess, notifyError } = useNotifyStore();
  const [parameters, setParameters] = useState<Record<string, unknown>>({});
  const [creating, setCreating] = useState(false);
  // The display name follows the chosen model until the user types their own.
  const displayNameEdited = useRef(false);
  const { selectedApp } = useDashboardStore();

  const form = useForm<CreateLLMInferenceInput>({
    resolver: zodResolver(createLLMInferenceSchema),
    defaultValues: emptyForm(DEFAULT_TYPE),
  });

  const type = form.watch('type');
  const llmModel = form.watch('llmModel');
  const modelType = form.watch('modelType');
  const providerConfig = getProviderConfig(type);

  // Reset everything when the dialog closes
  useEffect(() => {
    if (!isOpen) {
      form.reset(emptyForm(DEFAULT_TYPE));
      setParameters({});
      displayNameEdited.current = false;
    }
  }, [isOpen, form]);

  const changeProvider = (newType: InferenceEngineType) => {
    if (newType === type) return;
    const model = getDefaultModelId(newType);
    const preset = findModelPreset(newType, model);
    form.reset({
      ...emptyForm(newType),
      llmModel: model,
      displayName: displayNameEdited.current
        ? form.getValues('displayName')
        : preset?.id === model
          ? preset.label
          : model,
    });
    setParameters({});
  };

  const changeModel = (modelId: string) => {
    form.setValue('llmModel', modelId, { shouldValidate: true });
    if (!displayNameEdited.current) {
      const preset = findModelPreset(type, modelId);
      form.setValue('displayName', preset?.id === modelId ? preset.label : modelId, { shouldValidate: !!modelId });
    }
  };

  const onSubmit = async (data: CreateLLMInferenceInput) => {
    if (!appId) {
      notifyError('LLM inference config service not available');
      return;
    }

    setCreating(true);
    try {
      const { kept } = filterParameters(data.type, data.llmModel, data.modelType === 'llm' ? parameters : {});
      if (data.type === 'azure_openai' && data.apiVersion) {
        kept.api_version = data.apiVersion.trim();
      }
      if (data.type === 'bedrock') {
        kept.aws_region = data.awsRegion?.trim();
        if (data.awsAccessKeyId?.trim()) kept.aws_access_key_id = data.awsAccessKeyId.trim();
      }

      const response = await floConsoleService.llmInferenceService.createLLMConfig({
        display_name: data.displayName.trim(),
        llm_model: data.llmModel.trim(),
        api_key: data.apiKey?.trim() || undefined,
        type: data.type,
        model_type: data.modelType,
        base_url: (data.type !== 'bedrock' && data.baseUrl?.trim()) || undefined,
        parameters: Object.keys(kept).length > 0 ? kept : undefined,
      });

      notifySuccess('Model added to repository successfully');
      onSuccess?.();
      onOpenChange(false);

      const responseData = response.data?.data;
      if (responseData?.id) {
        navigate(`/apps/${appId}/llm-repository/${responseData.id}`);
      }
    } catch (error) {
      console.error('Error creating LLM inference config:', error);
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to add model to repository');
    } finally {
      setCreating(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl min-w-0 overflow-y-auto lg:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Add model</DialogTitle>
          <DialogDescription>Add a model to the repository for {selectedApp?.app_name}</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-8">
            <section className="flex flex-col gap-4">
              <SectionTitle title="Model" />
              <div className="grid gap-5 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="type"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Provider</FormLabel>
                      <ProviderSelect value={field.value} onChange={changeProvider} />
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="llmModel"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{providerConfig?.modelLabel ?? 'Model'}</FormLabel>
                      <ModelSelect provider={type} value={field.value} onChange={changeModel} />
                      {type === 'azure_openai' && (
                        <Input
                          value={field.value}
                          onChange={(e) => changeModel(e.target.value)}
                          placeholder="Deployment name, e.g. gpt-5.4-nano"
                          aria-label="Deployment name"
                        />
                      )}
                      {providerConfig?.modelHelp && (
                        <p className="frost-text-muted text-xs">{providerConfig.modelHelp}</p>
                      )}
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="displayName"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Display name</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="Shown wherever this model is picked"
                          {...field}
                          onChange={(e) => {
                            displayNameEdited.current = e.target.value.trim() !== '';
                            field.onChange(e);
                          }}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="modelType"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Used for</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
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
            </section>

            <section className="flex flex-col gap-4">
              <SectionTitle title="Connection" />
              <div className="grid gap-5 sm:grid-cols-2">
                {REQUIRES_API_KEY.includes(type) && (
                  <FormField
                    control={form.control}
                    name="apiKey"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>API key</FormLabel>
                        <FormControl>
                          <Input type="password" placeholder="Your API key" autoComplete="off" {...field} />
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
                      name="awsAccessKeyId"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Access key ID</FormLabel>
                          <FormControl>
                            <Input placeholder="AKIA..." autoComplete="off" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="apiKey"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Secret access key</FormLabel>
                          <FormControl>
                            <Input type="password" placeholder="Your secret access key" autoComplete="off" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="awsRegion"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Region</FormLabel>
                          <FormControl>
                            <Input placeholder="us-east-1" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </>
                )}

                {type !== 'bedrock' && (
                  <FormField
                    control={form.control}
                    name="baseUrl"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{type === 'azure_openai' ? 'Endpoint' : 'Base URL'}</FormLabel>
                        <FormControl>
                          <Input type="url" placeholder={BASE_URL_PLACEHOLDERS[type]} {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )}

                {type === 'azure_openai' && (
                  <FormField
                    control={form.control}
                    name="apiVersion"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>API version</FormLabel>
                        <FormControl>
                          <Input type="text" placeholder="2025-04-01-preview" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )}
              </div>
              <p className="frost-text-muted text-xs">
                {type === 'bedrock'
                  ? 'The secret access key is stored securely and never returned in API responses. Leave both keys empty to use the AWS credentials of the server running voice agents.'
                  : 'API keys are stored securely and never returned in API responses.'}
              </p>
            </section>

            {modelType === 'llm' && (
              <section className="frost-glass border-frost-border ring-frost-border flex flex-col gap-4 rounded-lg border p-5 ring-1">
                <SectionTitle
                  title="Settings"
                  description="Only the settings this model accepts are shown. Leave a field empty to use the provider's default."
                />
                {llmModel.trim() ? (
                  <ModelParameters
                    provider={type}
                    modelId={llmModel}
                    values={parameters}
                    onChange={(key, value) => setParameters((prev) => ({ ...prev, [key]: value }))}
                  />
                ) : (
                  <Alert variant="default">
                    <AlertDescription>Choose a model to see its settings.</AlertDescription>
                  </Alert>
                )}
              </section>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={creating || form.formState.isSubmitting}>
                Add model
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateLLMInferenceDialog;
