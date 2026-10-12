import { Button } from '@app/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@app/components/ui/command';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Popover, PopoverContent, PopoverTrigger } from '@app/components/ui/popover';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@app/components/ui/tabs';
import { Textarea } from '@app/components/ui/textarea';
import { Slider } from '@app/components/ui/slider';
import { Input } from '@app/components/ui/input';
import { cn } from '@app/lib/utils';
import { ToolsDetailsData } from '@app/types/tool';
import { useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import { popupCodeMirrorExtensions } from '@app/lib/code-mirror';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import yaml from 'js-yaml';
import { Check, ChevronsUpDown } from 'lucide-react';
import React, { useEffect, useState, useRef } from 'react';
import { useForm } from 'react-hook-form';
import { useParams } from 'react-router';
import { z } from 'zod';
import { useGetLLMConfigs } from '@app/hooks/data/fetch-hooks';

const editAgentSchema = z.object({
  yamlContent: z.string().min(1, 'YAML content is required'),
  selectedTools: z.array(z.object({ id: z.string(), value: z.string() })).optional(),

  // Identity & Metadata
  agentName: z.string().optional(),
  role: z.string().optional(),
  job: z.string().optional(),
  description: z.string().optional(),
  version: z.string().optional(),
  author: z.string().optional(),
  tags: z.string().optional(),
  actAs: z.string().optional(),

  // Model Config
  provider: z.string().optional(),
  modelName: z.string().optional(),
  modelId: z.string().optional(),
  baseUrl: z.string().optional(),
  project: z.string().optional(),
  location: z.string().optional(),
  apiKey: z.string().optional(),
  azureEndpoint: z.string().optional(),
  azureApiVersion: z.string().optional(),
  timeout: z.coerce.number().optional().nullable(),

  // Settings
  temperature: z.number().min(0).max(2).optional(),
  maxTokens: z.coerce.number().optional().nullable(),
  maxRetries: z.coerce.number().optional().nullable(),
  reasoningPattern: z.string().optional(),
  topP: z.coerce.number().min(0).max(1).optional().nullable(),
  topK: z.coerce.number().optional().nullable(),
  frequencyPenalty: z.coerce.number().min(-2).max(2).optional().nullable(),
  presencePenalty: z.coerce.number().min(-2).max(2).optional().nullable(),
  seed: z.coerce.number().optional().nullable(),
});

type EditAgentInput = z.infer<typeof editAgentSchema>;

interface EditAgentDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  yamlContent: string;
  selectedTools: { id: string; value: string }[];
  toolsDetails: ToolsDetailsData[];
  onSave: (
    yamlContent: string,
    selectedTools: { id: string; value: string }[],
    options: { createNewVersion: boolean }
  ) => Promise<void>;
  saving: boolean;
  /** The version currently being edited (for context in the header). */
  editingVersion?: number;
}

const REASONING_PATTERNS = [
  { value: 'DIRECT', label: 'Direct' },
  { value: 'REACT', label: 'ReAct' },
  { value: 'COT', label: 'Chain of Thought (COT)' },
];

const EditAgentDialog: React.FC<EditAgentDialogProps> = ({
  isOpen,
  onOpenChange,
  yamlContent: initialYamlContent,
  selectedTools: initialSelectedTools,
  toolsDetails,
  onSave,
  saving,
  editingVersion,
}) => {
  const { appId } = useParams<{ appId: string }>();
  const [localYamlContent, setLocalYamlContent] = useState(initialYamlContent);
  const [localSelectedTools, setLocalSelectedTools] = useState(initialSelectedTools);
  const [toolsComboboxOpen, setToolsComboboxOpen] = useState(false);
  const [submitAction, setSubmitAction] = useState<'save' | 'new' | null>(null);
  const [activeTab, setActiveTab] = useState<string>('visual');
  const isSyncingFromYaml = useRef(false);
  const { notifyError } = useNotifyStore();

  const { data: rootfloConfigs = [] } = useGetLLMConfigs(appId!);
  const rootfloModels = rootfloConfigs;

  const form = useForm<EditAgentInput>({
    resolver: zodResolver(editAgentSchema),
    defaultValues: {
      yamlContent: initialYamlContent,
      selectedTools: initialSelectedTools,
    },
  });

  const watchAllFields = form.watch();

  // Sync Visual -> YAML when in visual mode
  useEffect(() => {
    if (activeTab === 'visual' && isOpen && !isSyncingFromYaml.current) {
      const tagsArray = watchAllFields.tags
        ? watchAllFields.tags
            .split(',')
            .map((t: string) => t.trim())
            .filter(Boolean)
        : [];

      let agentYamlObj: Record<string, unknown> = {};
      try {
        agentYamlObj = (yaml.load(watchAllFields.yamlContent) as Record<string, unknown>) || {};
      } catch {
        return; // Ignore if unparseable
      }

      agentYamlObj.apiVersion = agentYamlObj.apiVersion || 'flo/alpha-v1';

      const metadata: Record<string, unknown> = (agentYamlObj.metadata as Record<string, unknown>) || {};
      agentYamlObj.metadata = metadata;

      metadata.version = watchAllFields.version || '1.0.0';

      const agent: Record<string, unknown> = (agentYamlObj.agent as Record<string, unknown>) || {};
      agentYamlObj.agent = agent;

      const model: Record<string, unknown> = (agent.model as Record<string, unknown>) || {};
      agent.model = model;

      const settings: Record<string, unknown> = (agent.settings as Record<string, unknown>) || {};
      agent.settings = settings;

      // Metadata
      if (watchAllFields.description) metadata.description = watchAllFields.description;
      else delete metadata.description;

      if (watchAllFields.author) metadata.author = watchAllFields.author;
      else delete metadata.author;

      if (tagsArray.length > 0) metadata.tags = tagsArray;
      else delete metadata.tags;

      // Identity
      if (watchAllFields.agentName) agent.name = watchAllFields.agentName;

      if (watchAllFields.role) agent.role = watchAllFields.role;
      else delete agent.role;

      if (watchAllFields.job) agent.job = watchAllFields.job;
      else delete agent.job;

      if (watchAllFields.actAs) agent.act_as = watchAllFields.actAs;
      else delete agent.act_as;

      // Provider specifics
      model.provider = 'rootflo';

      // Clear all modeled fields first to prevent leak when switching provider
      delete model.name;
      delete model.project;
      delete model.location;
      delete model.base_url;
      delete model.azure_endpoint;
      delete model.azure_api_version;
      delete model.api_key;
      delete model.timeout;

      model.model_id = watchAllFields.modelId || '';

      if (watchAllFields.provider === 'openai_vllm') {
        if (watchAllFields.apiKey) model.api_key = watchAllFields.apiKey;
      }

      if (watchAllFields.baseUrl && watchAllFields.provider !== 'vertexai') {
        model.base_url = watchAllFields.baseUrl;
      }
      if (watchAllFields.timeout) model.timeout = watchAllFields.timeout;

      // Settings
      if (watchAllFields.temperature !== undefined) settings.temperature = watchAllFields.temperature;
      else delete settings.temperature;

      if (watchAllFields.maxTokens) settings.max_tokens = watchAllFields.maxTokens;
      else delete settings.max_tokens;

      if (watchAllFields.maxRetries) settings.max_retries = watchAllFields.maxRetries;
      else delete settings.max_retries;

      if (watchAllFields.reasoningPattern) settings.reasoning_pattern = watchAllFields.reasoningPattern;
      else delete settings.reasoning_pattern;

      if (watchAllFields.topP !== undefined && watchAllFields.topP !== null) settings.top_p = watchAllFields.topP;
      else delete settings.top_p;

      if (watchAllFields.topK) settings.top_k = watchAllFields.topK;
      else delete settings.top_k;

      if (watchAllFields.frequencyPenalty !== undefined && watchAllFields.frequencyPenalty !== null)
        settings.frequency_penalty = watchAllFields.frequencyPenalty;
      else delete settings.frequency_penalty;

      if (watchAllFields.presencePenalty !== undefined && watchAllFields.presencePenalty !== null)
        settings.presence_penalty = watchAllFields.presencePenalty;
      else delete settings.presence_penalty;

      if (watchAllFields.seed) settings.seed = watchAllFields.seed;
      else delete settings.seed;

      // Cleanup empty settings
      if (Object.keys(settings).length === 0) {
        delete agent.settings;
      }

      try {
        const newYaml = yaml.dump(agentYamlObj);
        if (newYaml !== watchAllFields.yamlContent) {
          form.setValue('yamlContent', newYaml, { shouldValidate: true });
          setLocalYamlContent(newYaml);
        }
      } catch (e) {
        console.error('YAML dump failed', e);
      }
    }
  }, [watchAllFields, activeTab, form, isOpen]);

  const handleTabChange = (value: string) => {
    if (value === 'visual') {
      isSyncingFromYaml.current = true;
      try {
        const parsed = yaml.load(form.getValues('yamlContent')) as Record<string, Record<string, unknown>> | null;
        if (!parsed) {
          notifyError('Cannot switch to visual tab: YAML is empty or invalid.');
          return;
        }
        if (!parsed.agent) {
          notifyError('Cannot switch to visual tab: "agent" key is missing.');
          return;
        }
        if (parsed.agent) {
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
        notifyError('Cannot switch to visual tab: YAML parsing failed.');
        return;
      } finally {
        setTimeout(() => {
          isSyncingFromYaml.current = false;
        }, 0);
      }
    }
    setActiveTab(value);
  };

  useEffect(() => {
    if (isOpen) {
      form.reset({
        yamlContent: initialYamlContent,
        selectedTools: initialSelectedTools,
      });
      setLocalYamlContent(initialYamlContent);
      setLocalSelectedTools(initialSelectedTools);

      try {
        const parsed = yaml.load(initialYamlContent) as Record<string, Record<string, unknown>> | null;
        if (parsed && parsed.agent) {
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
      } catch (e) {
        console.error('Initial YAML parse failed', e);
      }

      setActiveTab('visual');
    }
  }, [initialYamlContent, initialSelectedTools, form, isOpen]);

  // Update YAML when tools change
  useEffect(() => {
    if (!localYamlContent || toolsDetails.length === 0) return;

    const tools = toolsDetails.filter((tool) =>
      localSelectedTools.some((selected) => selected.value === tool.display_name)
    );

    let parsedYaml: { agent?: { tools?: unknown[] } } | null | undefined;
    try {
      parsedYaml = yaml.load(localYamlContent) as { agent?: { tools?: unknown[] } } | null;
    } catch (error) {
      console.error('Failed to parse YAML:', error);
      // Let's not notify error here as it might be annoying while typing
      return;
    }

    if (parsedYaml && parsedYaml.agent) {
      if (!parsedYaml.agent.tools) {
        parsedYaml.agent.tools = [];
      }

      parsedYaml.agent.tools = tools.map((tool) => {
        const prefilledParams: Record<string, string> | undefined =
          tool.prefilled_values && tool.prefilled_values.length > 0
            ? tool.prefilled_values.reduce(
                (acc: Record<string, string>, obj: { [key: string]: string }) => {
                  return { ...acc, ...obj };
                },
                {} as Record<string, string>
              )
            : undefined;

        return {
          name: tool.name,
          prefilled_params: prefilledParams,
          name_override: tool.name,
          description_override: tool.description,
        };
      });

      const newYaml = yaml.dump(parsedYaml);
      if (newYaml !== localYamlContent) {
        setLocalYamlContent(newYaml);
        form.setValue('yamlContent', newYaml);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localSelectedTools, toolsDetails]);

  const onSubmit = async (data: EditAgentInput, createNewVersion: boolean) => {
    await onSave(data.yamlContent, data.selectedTools || [], { createNewVersion });
    setSubmitAction(null);
    onOpenChange(false);
  };

  const handleClose = () => {
    onOpenChange(false);
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="frost-dialog border-frost-border ring-frost-border flex max-h-[90vh] min-w-0 flex-col gap-0 overflow-hidden p-0 sm:max-w-3xl lg:max-w-4xl">
        <DialogHeader className="border-frost-border border-b p-6 pb-4">
          <DialogTitle className="frost-text">
            Edit Agent{editingVersion !== undefined ? ` (v${editingVersion})` : ''}
          </DialogTitle>
          <DialogDescription className="frost-text-muted">
            Update the agent configuration and tools. Use "Save" to overwrite this version, or "Save as new version" to
            branch a new, unpromoted version.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit((data) => onSubmit(data, false))} className="flex min-h-0 flex-1 flex-col">
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
                        name="agentName"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel className="frost-text">Agent Name</FormLabel>
                            <FormControl>
                              <Input placeholder="my-agent" className="frost-control" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

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
                    </div>

                    <div className="grid grid-cols-2 gap-6">
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
                    </div>

                    <div className="grid grid-cols-2 gap-6">
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

                      <FormField
                        control={form.control}
                        name="selectedTools"
                        render={({ field }) => (
                          <FormItem className="min-w-0">
                            <FormLabel className="frost-text">Add Tools</FormLabel>
                            <FormControl>
                              <Popover open={toolsComboboxOpen} onOpenChange={setToolsComboboxOpen}>
                                <PopoverTrigger asChild>
                                  <Button
                                    type="button"
                                    className="frost-control w-full min-w-0 justify-between"
                                    variant="outline"
                                    role="combobox"
                                    aria-expanded={toolsComboboxOpen}
                                  >
                                    <span className="truncate">Select Tools</span>
                                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                                  </Button>
                                </PopoverTrigger>
                                <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0" align="start">
                                  <Command>
                                    <CommandInput placeholder="Search tools..." />
                                    <CommandList>
                                      <CommandEmpty>No tools found.</CommandEmpty>
                                      <CommandGroup>
                                        {toolsDetails.map((tool) => {
                                          const isSelected = localSelectedTools.some(
                                            (selected) => selected.value === tool.display_name
                                          );
                                          return (
                                            <CommandItem
                                              key={tool.display_name}
                                              value={tool.display_name}
                                              onSelect={() => {
                                                let newSelectedTools;
                                                if (isSelected) {
                                                  newSelectedTools = localSelectedTools.filter(
                                                    (item) => item.value !== tool.display_name
                                                  );
                                                } else {
                                                  newSelectedTools = [
                                                    ...localSelectedTools,
                                                    { id: tool.display_name, value: tool.display_name },
                                                  ];
                                                }
                                                setLocalSelectedTools(newSelectedTools);
                                                field.onChange(newSelectedTools);
                                              }}
                                            >
                                              <Check
                                                className={cn('mr-2 h-4 w-4', isSelected ? 'opacity-100' : 'opacity-0')}
                                              />
                                              <span className="truncate">{tool.display_name}</span>
                                            </CommandItem>
                                          );
                                        })}
                                      </CommandGroup>
                                    </CommandList>
                                  </Command>
                                </PopoverContent>
                              </Popover>
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
                          <FormLabel className="frost-text">System Prompt / Job</FormLabel>
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
                          name="modelId"
                          render={({ field }) => (
                            <FormItem className="col-span-2">
                              <FormLabel className="frost-text">LLM Model</FormLabel>
                              <Select onValueChange={field.onChange} value={field.value}>
                                <FormControl>
                                  <SelectTrigger className="frost-control">
                                    <SelectValue placeholder="Select a RootFlo LLM model" />
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
                      </div>

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
                              value={localYamlContent}
                              onChange={(value) => {
                                setLocalYamlContent(value);
                                field.onChange(value);
                              }}
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

                  <div className="mt-4">
                    <FormField
                      control={form.control}
                      name="selectedTools"
                      render={({ field }) => (
                        <FormItem className="min-w-0">
                          <FormLabel className="frost-text">Add Tools (YAML View)</FormLabel>
                          <FormControl>
                            <Popover open={toolsComboboxOpen} onOpenChange={setToolsComboboxOpen}>
                              <PopoverTrigger asChild>
                                <Button
                                  type="button"
                                  className="frost-control w-full min-w-0 justify-between"
                                  variant="outline"
                                  role="combobox"
                                  aria-expanded={toolsComboboxOpen}
                                >
                                  <span className="truncate">Select Tools</span>
                                  <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                                </Button>
                              </PopoverTrigger>
                              <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0" align="start">
                                <Command>
                                  <CommandInput placeholder="Search tools..." />
                                  <CommandList>
                                    <CommandEmpty>No tools found.</CommandEmpty>
                                    <CommandGroup>
                                      {toolsDetails.map((tool) => {
                                        const isSelected = localSelectedTools.some(
                                          (selected) => selected.value === tool.display_name
                                        );
                                        return (
                                          <CommandItem
                                            key={tool.display_name}
                                            value={tool.display_name}
                                            onSelect={() => {
                                              let newSelectedTools;
                                              if (isSelected) {
                                                newSelectedTools = localSelectedTools.filter(
                                                  (item) => item.value !== tool.display_name
                                                );
                                              } else {
                                                newSelectedTools = [
                                                  ...localSelectedTools,
                                                  { id: tool.display_name, value: tool.display_name },
                                                ];
                                              }
                                              setLocalSelectedTools(newSelectedTools);
                                              field.onChange(newSelectedTools);
                                            }}
                                          >
                                            <Check
                                              className={cn('mr-2 h-4 w-4', isSelected ? 'opacity-100' : 'opacity-0')}
                                            />
                                            <span className="truncate">{tool.display_name}</span>
                                          </CommandItem>
                                        );
                                      })}
                                    </CommandGroup>
                                  </CommandList>
                                </Command>
                              </PopoverContent>
                            </Popover>
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </TabsContent>
              </div>

              <DialogFooter className="border-frost-border bg-frost-dialog/50 border-t p-4 backdrop-blur-md">
                <Button
                  type="button"
                  variant="outline"
                  className="frost-control border-frost-border"
                  onClick={handleClose}
                  disabled={saving}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="outline"
                  className="frost-control border-frost-border"
                  disabled={saving}
                  loading={saving && submitAction === 'save'}
                  onClick={() => setSubmitAction('save')}
                >
                  Save
                </Button>
                <Button
                  type="button"
                  disabled={saving}
                  loading={saving && submitAction === 'new'}
                  onClick={() => {
                    setSubmitAction('new');
                    form.handleSubmit((data) => onSubmit(data, true))();
                  }}
                >
                  Save as new version
                </Button>
              </DialogFooter>
            </Tabs>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default EditAgentDialog;
