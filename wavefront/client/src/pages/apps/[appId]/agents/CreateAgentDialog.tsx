import floConsoleService from '@app/api';
import { NamespaceItem } from '@app/api/namespace-service';
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@app/components/ui/tabs';
import { Textarea } from '@app/components/ui/textarea';
import { Slider } from '@app/components/ui/slider';
import { extractErrorMessage } from '@app/lib/utils';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import { popupCodeMirrorExtensions } from '@app/lib/code-mirror';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import yaml from 'js-yaml';
import { createAgentSchema, type CreateAgentInput } from './schemas';
import { useGetLLMConfigs } from '@app/hooks/data/fetch-hooks';

const defaultYamlContent = `apiVersion: flo/alpha-v1
metadata:
  name: translator-agent
  version: 1.0.0
  description: "Agent for translating text with specified tone"
  author: "Admin"
  tags: ["translation"]

agent:
  name: translator
  role: Professional Translator
  act_as: assistant
  model:
    provider: gemini
    name: gemini-2.5-flash
  settings:
    temperature: 0.7
  job: You are a translator. Use this tone <tone>
`;

interface CreateAgentDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  onSuccess?: () => void;
  namespaces: NamespaceItem[];
}

const PROVIDERS = [
  { value: 'gemini', label: 'Google (Gemini)' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'ollama', label: 'Ollama' },
  { value: 'rootflo', label: 'RootFlo' },
  { value: 'vertexai', label: 'Vertex AI' },
  { value: 'azure_openai', label: 'Azure OpenAI' },
  { value: 'openai_vllm', label: 'OpenAI vLLM' },
];

const REASONING_PATTERNS = [
  { value: 'DIRECT', label: 'Direct' },
  { value: 'REACT', label: 'ReAct' },
  { value: 'COT', label: 'Chain of Thought (COT)' },
];

const CreateAgentDialog: React.FC<CreateAgentDialogProps> = ({
  isOpen,
  onOpenChange,
  appId,
  onSuccess,
  namespaces,
}) => {
  const navigate = useNavigate();
  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();
  const [activeTab, setActiveTab] = useState<string>('visual');

  const { data: rootfloConfigs = [] } = useGetLLMConfigs(appId);
  const rootfloModels = rootfloConfigs;

  const form = useForm<CreateAgentInput>({
    resolver: zodResolver(createAgentSchema),
    defaultValues: {
      agentId: '',
      namespace: 'default',
      yamlContent: defaultYamlContent.trim(),
      agentName: 'translator',
      role: 'Professional Translator',
      job: 'You are a translator. Use this tone <tone>',
      provider: 'gemini',
      modelName: 'gemini-2.5-flash',
      temperature: 0.7,
      description: 'Agent for translating text with specified tone',
      version: '1.0.0',
      author: 'Admin',
      tags: 'translation',
      actAs: 'assistant',
      modelId: '',
    },
  });

  const watchAllFields = form.watch();

  // Sync Visual -> YAML when in visual mode
  useEffect(() => {
    if (activeTab === 'visual') {
      const tagsArray = watchAllFields.tags
        ? watchAllFields.tags
            .split(',')
            .map((t: string) => t.trim())
            .filter(Boolean)
        : [];

      const agentYamlObj: Record<string, unknown> = {
        apiVersion: 'flo/alpha-v1',
        metadata: {
          name: `${watchAllFields.agentId || 'my'}-agent`,
          version: watchAllFields.version || '1.0.0',
        },
        agent: {
          name: watchAllFields.agentName || watchAllFields.agentId || 'my-agent',
          model: {
            provider: watchAllFields.provider || 'gemini',
          },
          settings: {},
        },
      };

      // Optional Metadata
      if (watchAllFields.description) agentYamlObj.metadata.description = watchAllFields.description;
      if (watchAllFields.author) agentYamlObj.metadata.author = watchAllFields.author;
      if (tagsArray.length > 0) agentYamlObj.metadata.tags = tagsArray;

      // Optional Identity
      if (watchAllFields.role) agentYamlObj.agent.role = watchAllFields.role;
      if (watchAllFields.job) agentYamlObj.agent.job = watchAllFields.job;
      if (watchAllFields.actAs) agentYamlObj.agent.act_as = watchAllFields.actAs;

      // Provider specifics
      if (watchAllFields.provider === 'rootflo') {
        agentYamlObj.agent.model.model_id = watchAllFields.modelId || '';
      } else {
        agentYamlObj.agent.model.name = watchAllFields.modelName || 'gemini-2.5-flash';
      }

      if (watchAllFields.provider === 'vertexai') {
        if (watchAllFields.project) agentYamlObj.agent.model.project = watchAllFields.project;
        if (watchAllFields.location) agentYamlObj.agent.model.location = watchAllFields.location;
        if (watchAllFields.baseUrl) agentYamlObj.agent.model.base_url = watchAllFields.baseUrl;
      }

      if (watchAllFields.provider === 'azure_openai') {
        if (watchAllFields.azureEndpoint) agentYamlObj.agent.model.azure_endpoint = watchAllFields.azureEndpoint;
        if (watchAllFields.azureApiVersion) agentYamlObj.agent.model.azure_api_version = watchAllFields.azureApiVersion;
      }

      if (watchAllFields.provider === 'openai_vllm') {
        if (watchAllFields.apiKey) agentYamlObj.agent.model.api_key = watchAllFields.apiKey;
      }

      if (watchAllFields.baseUrl && watchAllFields.provider !== 'vertexai') {
        agentYamlObj.agent.model.base_url = watchAllFields.baseUrl;
      }
      if (watchAllFields.timeout) agentYamlObj.agent.model.timeout = watchAllFields.timeout;

      // Settings
      if (watchAllFields.temperature !== undefined)
        agentYamlObj.agent.settings.temperature = watchAllFields.temperature;
      if (watchAllFields.maxTokens) agentYamlObj.agent.settings.max_tokens = watchAllFields.maxTokens;
      if (watchAllFields.maxRetries) agentYamlObj.agent.settings.max_retries = watchAllFields.maxRetries;
      if (watchAllFields.reasoningPattern)
        agentYamlObj.agent.settings.reasoning_pattern = watchAllFields.reasoningPattern;
      if (watchAllFields.topP !== undefined && watchAllFields.topP !== null)
        agentYamlObj.agent.settings.top_p = watchAllFields.topP;
      if (watchAllFields.topK) agentYamlObj.agent.settings.top_k = watchAllFields.topK;
      if (watchAllFields.frequencyPenalty !== undefined && watchAllFields.frequencyPenalty !== null)
        agentYamlObj.agent.settings.frequency_penalty = watchAllFields.frequencyPenalty;
      if (watchAllFields.presencePenalty !== undefined && watchAllFields.presencePenalty !== null)
        agentYamlObj.agent.settings.presence_penalty = watchAllFields.presencePenalty;
      if (watchAllFields.seed) agentYamlObj.agent.settings.seed = watchAllFields.seed;

      // Cleanup empty settings
      if (Object.keys(agentYamlObj.agent.settings).length === 0) {
        delete agentYamlObj.agent.settings;
      }

      try {
        const newYaml = yaml.dump(agentYamlObj);
        if (newYaml !== watchAllFields.yamlContent) {
          form.setValue('yamlContent', newYaml, { shouldValidate: true });
        }
      } catch (e) {
        console.error('YAML dump failed', e);
      }
    }
  }, [watchAllFields, activeTab, form]);

  const handleTabChange = (value: string) => {
    if (value === 'visual') {
      try {
        const parsed = yaml.load(form.getValues('yamlContent')) as Record<string, Record<string, unknown>> | null;
        if (parsed?.agent) {
          form.setValue('agentName', (parsed.agent.name as string) || '');
          form.setValue('role', (parsed.agent.role as string) || '');
          form.setValue('job', (parsed.agent.job as string) || (parsed.agent.prompt as string) || '');
          form.setValue('actAs', (parsed.agent.act_as as string) || 'assistant');

          if (parsed.agent.model) {
            const model = parsed.agent.model as Record<string, unknown>;
            form.setValue('provider', (model.provider as string) || '');
            form.setValue('modelName', (model.name as string) || '');
            form.setValue('modelId', (model.model_id as string) || '');
            form.setValue('baseUrl', (model.base_url as string) || '');
            form.setValue('project', (model.project as string) || '');
            form.setValue('location', (model.location as string) || '');
            form.setValue('apiKey', (model.api_key as string) || '');
            form.setValue('azureEndpoint', (model.azure_endpoint as string) || '');
            form.setValue('azureApiVersion', (model.azure_api_version as string) || '');
            form.setValue('timeout', (model.timeout as number) || null);
          }
          if (parsed.agent.settings) {
            const settings = parsed.agent.settings as Record<string, unknown>;
            form.setValue('temperature', (settings.temperature as number) ?? 0.7);
            form.setValue('maxTokens', (settings.max_tokens as number) || null);
            form.setValue('maxRetries', (settings.max_retries as number) || null);
            form.setValue('reasoningPattern', (settings.reasoning_pattern as string) || '');
            form.setValue('topP', (settings.top_p as number) ?? null);
            form.setValue('topK', (settings.top_k as number) || null);
            form.setValue('frequencyPenalty', (settings.frequency_penalty as number) ?? null);
            form.setValue('presencePenalty', (settings.presence_penalty as number) ?? null);
            form.setValue('seed', (settings.seed as number) || null);
          }
        }
        if (parsed?.metadata) {
          const metadata = parsed.metadata as Record<string, unknown>;
          form.setValue('description', (metadata.description as string) || '');
          form.setValue('version', (metadata.version as string) || '1.0.0');
          form.setValue('author', (metadata.author as string) || '');
          form.setValue('tags', Array.isArray(metadata.tags) ? metadata.tags.join(', ') : '');
        }
      } catch {
        // Ignored
      }
    }
    setActiveTab(value);
  };

  useEffect(() => {
    if (!isOpen) {
      form.reset({
        agentId: '',
        namespace: 'default',
        yamlContent: defaultYamlContent.trim(),
        agentName: 'translator',
        role: 'Professional Translator',
        job: 'You are a translator. Use this tone <tone>',
        provider: 'gemini',
        modelName: 'gemini-2.5-flash',
        temperature: 0.7,
        description: 'Agent for translating text with specified tone',
        version: '1.0.0',
        author: 'Admin',
        tags: 'translation',
        actAs: 'assistant',
        modelId: '',
      });
      setActiveTab('visual');
    }
  }, [isOpen, form]);

  const onSubmit = async (data: CreateAgentInput) => {
    try {
      const response = await floConsoleService.agentService.createAgent(data.agentId, data.yamlContent, data.namespace);

      if (response.data?.meta?.status === 'success' && response.data.data?.data) {
        const createdAgentId = response.data.data.data.id;
        notifySuccess('Agent created successfully');
        if (onSuccess) onSuccess();
        onOpenChange(false);
        if (createdAgentId) navigate(`/apps/${appId}/agents/${createdAgentId}`);
      }
    } catch (error) {
      console.error('Error creating agent:', error);
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to create agent');
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="frost-dialog border-frost-border ring-frost-border flex max-h-[90vh] min-w-0 flex-col gap-0 overflow-hidden p-0 sm:max-w-3xl lg:max-w-4xl">
        <DialogHeader className="border-frost-border border-b p-6 pb-4">
          <DialogTitle className="frost-text">Create New Agent</DialogTitle>
          <DialogDescription className="frost-text-muted">
            Create a new AI agent for {selectedApp?.app_name}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex min-h-0 flex-1 flex-col">
            <Tabs value={activeTab} onValueChange={handleTabChange} className="flex min-h-0 flex-1 flex-col">
              <div className="px-6">
                <TabsList className="border-frost-border flex h-auto w-full justify-start gap-6 rounded-none border-b bg-transparent p-0">
                  <TabsTrigger
                    value="visual"
                    className="data-[state=active]:border-primary frost-text -mb-px rounded-none border-b-2 border-transparent px-0 py-3 data-[state=active]:bg-transparent data-[state=active]:shadow-none [&_[data-tab-underline]]:!hidden"
                  >
                    Agent Builder
                  </TabsTrigger>
                  <TabsTrigger
                    value="yaml"
                    className="data-[state=active]:border-primary frost-text -mb-px rounded-none border-b-2 border-transparent px-0 py-3 data-[state=active]:bg-transparent data-[state=active]:shadow-none [&_[data-tab-underline]]:!hidden"
                  >
                    YAML Code
                  </TabsTrigger>
                </TabsList>
              </div>

              <div className="min-h-[400px] flex-1 overflow-y-auto p-6">
                <TabsContent value="visual" className="m-0 space-y-8 outline-none">
                  {/* METADATA SECTION */}
                  <section className="space-y-4">
                    <h3 className="frost-text flex items-center gap-2 text-lg font-medium">Identity & Metadata</h3>

                    <div className="grid grid-cols-2 gap-6">
                      <FormField
                        control={form.control}
                        name="agentId"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel className="frost-text">
                              Agent Name <span className="text-red-500">*</span>
                            </FormLabel>
                            <FormControl>
                              <Input placeholder="my-agent" className="frost-control" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name="namespace"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel className="frost-text">Namespace</FormLabel>
                            <Select onValueChange={field.onChange} value={field.value}>
                              <FormControl>
                                <SelectTrigger className="frost-control">
                                  <SelectValue placeholder="Select namespace" />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                {namespaces.length === 0 && <SelectItem value="default">default</SelectItem>}
                                {namespaces.map((ns) => (
                                  <SelectItem key={ns.name} value={ns.name}>
                                    {ns.name}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-6">
                      <FormField
                        control={form.control}
                        name="role"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel className="frost-text">Role</FormLabel>
                            <FormControl>
                              <Input placeholder="e.g. Senior Software Engineer" className="frost-control" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name="actAs"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel className="frost-text">Act As</FormLabel>
                            <Select onValueChange={field.onChange} value={field.value || 'assistant'}>
                              <FormControl>
                                <SelectTrigger className="frost-control">
                                  <SelectValue placeholder="Select act as" />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                <SelectItem value="assistant">Assistant</SelectItem>
                                <SelectItem value="user">User</SelectItem>
                                <SelectItem value="system">System</SelectItem>
                              </SelectContent>
                            </Select>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-6">
                      <FormField
                        control={form.control}
                        name="description"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel className="frost-text">Description</FormLabel>
                            <FormControl>
                              <Input
                                placeholder="Brief description of the agent"
                                className="frost-control"
                                {...field}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      <FormField
                        control={form.control}
                        name="tags"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel className="frost-text">Tags (Comma Separated)</FormLabel>
                            <FormControl>
                              <Input placeholder="tag1, tag2" className="frost-control" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>

                    <FormField
                      control={form.control}
                      name="job"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel className="frost-text">
                            System Prompt / Job <span className="text-red-500">*</span>
                          </FormLabel>
                          <FormControl>
                            <Textarea
                              rows={4}
                              placeholder="You are a helpful assistant..."
                              className="frost-control"
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </section>

                  {/* MODEL CONFIGURATION SECTION */}
                  <section className="space-y-4">
                    <h3 className="frost-text flex items-center gap-2 text-lg font-medium">Model Configuration</h3>

                    <div className="frost-card ring-frost-border space-y-6 rounded-2xl border p-6 ring-1">
                      <div className="grid grid-cols-2 gap-6">
                        <FormField
                          control={form.control}
                          name="provider"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel className="frost-text">
                                Provider <span className="text-red-500">*</span>
                              </FormLabel>
                              <Select onValueChange={field.onChange} value={field.value}>
                                <FormControl>
                                  <SelectTrigger className="frost-control">
                                    <SelectValue placeholder="Select provider" />
                                  </SelectTrigger>
                                </FormControl>
                                <SelectContent>
                                  {PROVIDERS.map((p) => (
                                    <SelectItem key={p.value} value={p.value}>
                                      {p.label}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        {watchAllFields.provider === 'rootflo' ? (
                          <FormField
                            control={form.control}
                            name="modelId"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel className="frost-text">
                                  RootFlo Model <span className="text-red-500">*</span>
                                </FormLabel>
                                <Select onValueChange={field.onChange} value={field.value}>
                                  <FormControl>
                                    <SelectTrigger className="frost-control">
                                      <SelectValue placeholder="Select a RootFlo model" />
                                    </SelectTrigger>
                                  </FormControl>
                                  <SelectContent>
                                    {rootfloModels.map(
                                      (model: { id: string; display_name?: string; llm_model?: string }) => (
                                        <SelectItem key={model.id} value={model.id}>
                                          {model.display_name || model.llm_model || model.id}
                                        </SelectItem>
                                      )
                                    )}
                                  </SelectContent>
                                </Select>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        ) : (
                          <FormField
                            control={form.control}
                            name="modelName"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel className="frost-text">
                                  Model Name <span className="text-red-500">*</span>
                                </FormLabel>
                                <FormControl>
                                  <Input placeholder="e.g. gemini-2.5-flash" className="frost-control" {...field} />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        )}
                      </div>

                      {watchAllFields.provider === 'vertexai' && (
                        <div className="grid grid-cols-2 gap-6">
                          <FormField
                            control={form.control}
                            name="project"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel className="frost-text">GCP Project ID</FormLabel>
                                <FormControl>
                                  <Input placeholder="my-gcp-project" className="frost-control" {...field} />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                          <FormField
                            control={form.control}
                            name="location"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel className="frost-text">GCP Location</FormLabel>
                                <FormControl>
                                  <Input placeholder="us-central1" className="frost-control" {...field} />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </div>
                      )}

                      {watchAllFields.provider === 'azure_openai' && (
                        <div className="grid grid-cols-2 gap-6">
                          <FormField
                            control={form.control}
                            name="azureEndpoint"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel className="frost-text">Azure Endpoint</FormLabel>
                                <FormControl>
                                  <Input
                                    placeholder="https://my-resource.openai.azure.com"
                                    className="frost-control"
                                    {...field}
                                  />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                          <FormField
                            control={form.control}
                            name="azureApiVersion"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel className="frost-text">Azure API Version</FormLabel>
                                <FormControl>
                                  <Input placeholder="2024-02-15-preview" className="frost-control" {...field} />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </div>
                      )}

                      {watchAllFields.provider === 'openai_vllm' && (
                        <div className="grid grid-cols-1 gap-6">
                          <FormField
                            control={form.control}
                            name="apiKey"
                            render={({ field }) => (
                              <FormItem>
                                <FormLabel className="frost-text">API Key</FormLabel>
                                <FormControl>
                                  <Input type="password" placeholder="sk-..." className="frost-control" {...field} />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        </div>
                      )}

                      <div className="grid grid-cols-2 gap-6">
                        <FormField
                          control={form.control}
                          name="baseUrl"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel className="frost-text">Base URL (Custom Endpoint)</FormLabel>
                              <FormControl>
                                <Input placeholder="http://localhost:11434" className="frost-control" {...field} />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                        <FormField
                          control={form.control}
                          name="timeout"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel className="frost-text">Timeout (seconds)</FormLabel>
                              <FormControl>
                                <Input
                                  type="number"
                                  placeholder="60"
                                  className="frost-control"
                                  value={field.value || ''}
                                  onChange={(e) => field.onChange(e.target.value ? Number(e.target.value) : null)}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>
                    </div>
                  </section>

                  {/* ADVANCED SETTINGS SECTION */}
                  <section className="space-y-4">
                    <h3 className="frost-text flex items-center gap-2 text-lg font-medium">
                      Advanced Generation Settings
                    </h3>

                    <div className="frost-card ring-frost-border space-y-6 rounded-2xl border p-6 ring-1">
                      <div className="grid grid-cols-2 gap-6">
                        <FormField
                          control={form.control}
                          name="temperature"
                          render={({ field }) => (
                            <FormItem>
                              <div className="mb-2 flex items-center justify-between">
                                <FormLabel className="frost-text m-0">Temperature</FormLabel>
                                <span className="frost-text-muted text-xs">{field.value}</span>
                              </div>
                              <FormControl>
                                <Slider
                                  min={0}
                                  max={2}
                                  step={0.1}
                                  value={[field.value ?? 0.7]}
                                  onValueChange={(val) => field.onChange(val[0])}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="reasoningPattern"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel className="frost-text">Reasoning Pattern</FormLabel>
                              <Select onValueChange={field.onChange} value={field.value || ''}>
                                <FormControl>
                                  <SelectTrigger className="frost-control">
                                    <SelectValue placeholder="Select pattern" />
                                  </SelectTrigger>
                                </FormControl>
                                <SelectContent>
                                  {REASONING_PATTERNS.map((p) => (
                                    <SelectItem key={p.value} value={p.value}>
                                      {p.label}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>

                      <div className="grid grid-cols-3 gap-6">
                        <FormField
                          control={form.control}
                          name="maxTokens"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel className="frost-text">Max Tokens</FormLabel>
                              <FormControl>
                                <Input
                                  type="number"
                                  placeholder="Default"
                                  className="frost-control"
                                  value={field.value || ''}
                                  onChange={(e) => field.onChange(e.target.value ? Number(e.target.value) : null)}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="topK"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel className="frost-text">Top K</FormLabel>
                              <FormControl>
                                <Input
                                  type="number"
                                  placeholder="Default"
                                  className="frost-control"
                                  value={field.value || ''}
                                  onChange={(e) => field.onChange(e.target.value ? Number(e.target.value) : null)}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="topP"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel className="frost-text">Top P (0.0 to 1.0)</FormLabel>
                              <FormControl>
                                <Input
                                  type="number"
                                  step="0.1"
                                  placeholder="Default"
                                  className="frost-control"
                                  value={field.value || ''}
                                  onChange={(e) => field.onChange(e.target.value ? Number(e.target.value) : null)}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>

                      <div className="grid grid-cols-3 gap-6">
                        <FormField
                          control={form.control}
                          name="frequencyPenalty"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel className="frost-text">Freq. Penalty</FormLabel>
                              <FormControl>
                                <Input
                                  type="number"
                                  step="0.1"
                                  placeholder="0.0"
                                  className="frost-control"
                                  value={field.value || ''}
                                  onChange={(e) => field.onChange(e.target.value ? Number(e.target.value) : null)}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="presencePenalty"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel className="frost-text">Pres. Penalty</FormLabel>
                              <FormControl>
                                <Input
                                  type="number"
                                  step="0.1"
                                  placeholder="0.0"
                                  className="frost-control"
                                  value={field.value || ''}
                                  onChange={(e) => field.onChange(e.target.value ? Number(e.target.value) : null)}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="seed"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel className="frost-text">Seed</FormLabel>
                              <FormControl>
                                <Input
                                  type="number"
                                  placeholder="Random"
                                  className="frost-control"
                                  value={field.value || ''}
                                  onChange={(e) => field.onChange(e.target.value ? Number(e.target.value) : null)}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>
                    </div>
                  </section>
                </TabsContent>

                <TabsContent value="yaml" className="m-0 h-full outline-none">
                  <FormField
                    control={form.control}
                    name="yamlContent"
                    render={({ field }) => (
                      <FormItem className="flex h-full flex-col">
                        <FormControl>
                          <div className="frost-control border-frost-border w-full min-w-0 flex-1 overflow-hidden rounded-md border">
                            <CodeMirror
                              value={field.value}
                              onChange={field.onChange}
                              theme="dark"
                              height="100%"
                              className="h-full min-h-[400px] w-full"
                              extensions={[langs.yaml(), ...popupCodeMirrorExtensions]}
                              placeholder="Enter your agent YAML configuration..."
                            />
                          </div>
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </TabsContent>
              </div>

              <DialogFooter className="border-frost-border bg-frost-dialog/50 border-t p-4 backdrop-blur-md">
                <Button
                  type="button"
                  variant="outline"
                  className="frost-control border-frost-border"
                  onClick={() => onOpenChange(false)}
                >
                  Cancel
                </Button>
                <Button type="submit" loading={form.formState.isSubmitting}>
                  Create Agent
                </Button>
              </DialogFooter>
            </Tabs>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateAgentDialog;
