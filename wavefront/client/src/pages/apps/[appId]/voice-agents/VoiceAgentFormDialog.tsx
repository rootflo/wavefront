import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import ConversationConfigField from './ConversationConfigField';
import ConversationConfigGuide from './ConversationConfigGuide';
import VoiceAgentToolsManager, { PendingAgentTool } from './VoiceAgentToolsManager';
import { DEFAULT_EDITOR_TEXT, fromEditorText, toEditorText } from './conversation-config';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Checkbox } from '@app/components/ui/checkbox';
import { Label } from '@app/components/ui/label';
import { Slider } from '@app/components/ui/slider';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@app/components/ui/tabs';
import { useGetLLMConfigs, useGetSttConfigs, useGetTelephonyConfigs, useGetTtsConfigs } from '@app/hooks';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { CreateVoiceAgentRequest, UpdateVoiceAgentRequest, VoiceAgent } from '@app/types/voice-agent';
import { SUPPORTED_LANGUAGES, getLanguageDisplayName } from '@app/constants/languages';
import FieldHelp from '@app/components/FieldHelp';
import { VoiceIdsSection } from './VoiceIdsSection';
import { getTelephonyProviderConfig } from '@app/config/telephony-providers';
import {
  getProviderConfig,
  getVoiceProviderLabel,
  groupParamKeys,
  initializeParameters,
} from '@app/config/voice-providers';
import { TelephonyProvider } from '@app/types/telephony-config';
import {
  getBooleanParameterWithDefault,
  getNumberOrStringParameter,
  getNumberParameterWithDefault,
  getStringParameter,
} from '@app/utils/parameter-helpers';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useMemo, useState } from 'react';
import { FieldErrors, useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { z } from 'zod';
import { useCreateVoiceAgent, useUpdateVoiceAgent } from '@app/hooks';

const E164_REGEX = /^\+[1-9]\d{1,14}$/;

const FORM_TAB = {
  BASIC: 'basic',
  CONFIGURATIONS: 'configurations',
  LANGUAGES: 'languages',
  BEHAVIOR: 'behavior',
  TOOLS: 'tools',
  ADVANCED: 'advanced',
  GUIDE: 'guide',
} as const;

type FormTab = (typeof FORM_TAB)[keyof typeof FORM_TAB];

const isFormTab = (value: string): value is FormTab => Object.values(FORM_TAB).includes(value as FormTab);

// Voice IDs are required for a new agent; an existing one can be saved without touching them
const buildSchema = (isEdit: boolean) =>
  z.object({
    name: z.string().min(1, 'Name is required').max(100, 'Name must be 100 characters or less'),
    description: z.string().max(500, 'Description must be 500 characters or less').optional(),
    llm_config_id: z.string().min(1, 'Model is required'),
    tts_config_id: z.string().min(1, 'TTS configuration is required'),
    stt_config_id: z.string().min(1, 'STT configuration is required'),
    telephony_config_id: z.string().min(1, 'Telephony configuration is required'),
    tts_voice_ids: isEdit
      ? z.record(z.string(), z.string())
      : z
          .record(z.string(), z.string().min(1, 'Voice ID must not be empty'))
          .refine((val) => Object.keys(val).length > 0, {
            message: 'At least one voice ID is required',
          }),
    system_prompt: z.string().min(1, 'System prompt is required'),
    welcome_message: z.string(),
    conversation_config: z.string().optional(),
    status: z.enum(['active', 'inactive']),
    inbound_numbers: z.string().optional(),
    outbound_numbers: z.string().optional(),
    supported_languages: z.array(z.string()).min(1, 'At least one language is required'),
    default_language: z.string().min(1, 'Default language is required'),
  });

type VoiceAgentInput = z.infer<ReturnType<typeof buildSchema>>;

const FIELD_TAB_MAP: Record<keyof VoiceAgentInput, FormTab> = {
  name: FORM_TAB.BASIC,
  description: FORM_TAB.BASIC,
  status: FORM_TAB.BASIC,
  llm_config_id: FORM_TAB.CONFIGURATIONS,
  tts_config_id: FORM_TAB.CONFIGURATIONS,
  stt_config_id: FORM_TAB.CONFIGURATIONS,
  telephony_config_id: FORM_TAB.CONFIGURATIONS,
  tts_voice_ids: FORM_TAB.CONFIGURATIONS,
  inbound_numbers: FORM_TAB.BASIC,
  outbound_numbers: FORM_TAB.BASIC,
  supported_languages: FORM_TAB.LANGUAGES,
  default_language: FORM_TAB.LANGUAGES,
  system_prompt: FORM_TAB.BEHAVIOR,
  welcome_message: FORM_TAB.BEHAVIOR,
  conversation_config: FORM_TAB.ADVANCED,
};

const toFormValues = (agent?: VoiceAgent): VoiceAgentInput => ({
  name: agent?.name ?? '',
  description: agent?.description || '',
  llm_config_id: agent?.llm_config_id ?? '',
  tts_config_id: agent?.tts_config_id ?? '',
  stt_config_id: agent?.stt_config_id ?? '',
  telephony_config_id: agent?.telephony_config_id ?? '',
  tts_voice_ids: agent?.tts_voice_ids ?? { en: '' },
  system_prompt: agent?.system_prompt ?? '',
  welcome_message: agent?.welcome_message ?? '',
  conversation_config: agent ? toEditorText(agent.conversation_config) : DEFAULT_EDITOR_TEXT,
  status: agent?.status ?? 'inactive',
  inbound_numbers: agent?.inbound_numbers?.join(', ') || '',
  outbound_numbers: agent?.outbound_numbers?.join(', ') || '',
  supported_languages: agent?.supported_languages || ['en'],
  default_language: agent?.default_language || 'en',
});

/** Per-language voices count as customized once they stop being one shared voice. */
const hasCustomVoices = (agent?: VoiceAgent) => {
  const ids = Object.values(agent?.tts_voice_ids || {});
  return ids.length > 1 && new Set(ids).size > 1;
};

type ParameterKind = 'tts' | 'stt';

const SUBMIT_LABEL = { create: 'Create Voice Agent', edit: 'Update Voice Agent' };

interface VoiceAgentFormDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  /** The agent to edit; omit to create one. Render separate instances for create and edit. */
  agent?: VoiceAgent;
}

const VoiceAgentFormDialog: React.FC<VoiceAgentFormDialogProps> = ({ isOpen, onOpenChange, appId, agent }) => {
  const navigate = useNavigate();
  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();
  const createVoiceAgent = useCreateVoiceAgent(appId);
  const updateVoiceAgent = useUpdateVoiceAgent(appId);
  const isEdit = !!agent;
  const saving = createVoiceAgent.isPending || updateVoiceAgent.isPending;
  const [activeTab, setActiveTab] = useState<FormTab>(FORM_TAB.BASIC);
  const [ttsParameters, setTtsParameters] = useState<Record<string, unknown>>({});
  const [sttParameters, setSttParameters] = useState<Record<string, unknown>>({});
  const [voiceIdState, setVoiceIdState] = useState<Record<string, string>>(agent?.tts_voice_ids || { en: '' });
  const [customizeVoicesPerLanguage, setCustomizeVoicesPerLanguage] = useState(() => hasCustomVoices(agent));
  // Tools picked before a new agent exists; an existing agent attaches them directly
  const [pendingTools, setPendingTools] = useState<PendingAgentTool[]>([]);

  // Fetch configs for dropdowns
  const { data: llmConfigs = [] } = useGetLLMConfigs(appId);
  const { data: ttsConfigs = [] } = useGetTtsConfigs(appId);
  const { data: sttConfigs = [] } = useGetSttConfigs(appId);
  const { data: telephonyConfigs = [] } = useGetTelephonyConfigs(appId);

  const schema = useMemo(() => buildSchema(isEdit), [isEdit]);
  const form = useForm<VoiceAgentInput>({
    resolver: zodResolver(schema),
    defaultValues: toFormValues(agent),
  });

  // Watch config selections to determine providers
  const watchedTtsConfigId = form.watch('tts_config_id');
  const watchedSttConfigId = form.watch('stt_config_id');
  const watchedSupportedLanguages = form.watch('supported_languages');

  // Get selected providers
  const selectedTtsProvider = ttsConfigs.find((c) => c.id === watchedTtsConfigId)?.provider;
  const selectedSttProvider = sttConfigs.find((c) => c.id === watchedSttConfigId)?.provider;

  // The providers the agent was saved with, so its stored settings load only while those stay selected
  const savedTtsProvider = ttsConfigs.find((c) => c.id === agent?.tts_config_id)?.provider;
  const savedSttProvider = sttConfigs.find((c) => c.id === agent?.stt_config_id)?.provider;

  // A provider starts from its defaults; the saved provider of an existing agent starts from its stored values
  useEffect(() => {
    if (!isOpen || !selectedTtsProvider) return;
    setTtsParameters(
      agent && selectedTtsProvider === savedTtsProvider
        ? agent.tts_parameters || {}
        : initializeParameters('tts', selectedTtsProvider)
    );
  }, [selectedTtsProvider, savedTtsProvider, agent, isOpen]);

  useEffect(() => {
    if (!isOpen || !selectedSttProvider) return;
    setSttParameters(
      agent && selectedSttProvider === savedSttProvider
        ? agent.stt_parameters || {}
        : initializeParameters('stt', selectedSttProvider)
    );
  }, [selectedSttProvider, savedSttProvider, agent, isOpen]);

  // Sync voice ID state with language changes (keep shared default when not customizing)
  useEffect(() => {
    if (isOpen && watchedSupportedLanguages) {
      setVoiceIdState((prev) => {
        const shared = Object.values(prev).find((value) => value) || '';
        const newState: Record<string, string> = {};
        watchedSupportedLanguages.forEach((lang) => {
          newState[lang] = customizeVoicesPerLanguage ? prev[lang] || shared : shared || prev[lang] || '';
        });
        form.setValue('tts_voice_ids', newState);
        return newState;
      });
    }
  }, [watchedSupportedLanguages, isOpen, customizeVoicesPerLanguage, form]);

  // Start from the agent being edited, or a blank form, each time the dialog opens
  useEffect(() => {
    if (isOpen) {
      form.reset(toFormValues(agent));
      setVoiceIdState(agent?.tts_voice_ids || { en: '' });
      setCustomizeVoicesPerLanguage(hasCustomVoices(agent));
      setPendingTools([]);
      setActiveTab(FORM_TAB.BASIC);
    } else {
      setTtsParameters({});
      setSttParameters({});
    }
  }, [isOpen, agent, form]);

  const onInvalid = (errors: FieldErrors<VoiceAgentInput>) => {
    const firstErrorField = Object.keys(errors)[0] as keyof VoiceAgentInput | undefined;
    if (firstErrorField && FIELD_TAB_MAP[firstErrorField]) {
      setActiveTab(FIELD_TAB_MAP[firstErrorField]);
    }
  };

  const onSubmit = (data: VoiceAgentInput) => {
    // Validate JSON if provided
    const conversationConfig = fromEditorText(data.conversation_config);
    if (conversationConfig === undefined) {
      notifyError('Conversation configuration must be a valid JSON object');
      return;
    }

    // Build TTS parameters (filter out empty values + unsupported keys)
    const allowedTtsKeys = new Set(
      Object.keys(ttsProviderConfig?.parameters ?? {}).filter((key) => key !== 'language')
    );
    const builtTtsParameters: Record<string, unknown> = {};
    Object.entries(ttsParameters).forEach(([key, value]) => {
      if (allowedTtsKeys.has(key) && value !== '' && value !== undefined && value !== null) {
        builtTtsParameters[key] = value;
      }
    });

    // Build STT parameters (filter out empty values + unsupported keys)
    const allowedSttKeys = new Set(
      Object.keys(sttProviderConfig?.parameters ?? {}).filter((key) => key !== 'language')
    );
    const builtSttParameters: Record<string, unknown> = {};
    Object.entries(sttParameters).forEach(([key, value]) => {
      if (allowedSttKeys.has(key) && value !== '' && value !== undefined && value !== null) {
        builtSttParameters[key] = value;
      }
    });

    // Parse phone numbers (comma-separated)
    const parsePhoneNumbers = (input: string): string[] => {
      if (!input.trim()) return [];
      return input
        .split(',')
        .map((num) => num.trim())
        .filter((num) => num);
    };

    const inboundNumbers = parsePhoneNumbers(data.inbound_numbers || '');
    const outboundNumbers = parsePhoneNumbers(data.outbound_numbers || '');

    // Validate E.164 format
    const invalidInbound = inboundNumbers.filter((num) => !E164_REGEX.test(num));
    const invalidOutbound = outboundNumbers.filter((num) => !E164_REGEX.test(num));

    if (invalidInbound.length > 0) {
      notifyError(`Invalid inbound phone numbers (must be E.164 format): ${invalidInbound.join(', ')}`);
      return;
    }

    if (invalidOutbound.length > 0) {
      notifyError(`Invalid outbound phone numbers (must be E.164 format): ${invalidOutbound.join(', ')}`);
      return;
    }

    // Validate default language is in supported languages
    if (!data.supported_languages.includes(data.default_language)) {
      notifyError('Default language must be one of the supported languages');
      return;
    }

    if (agent) {
      // Build partial update - only include changed fields
      const requestData: Partial<UpdateVoiceAgentRequest> = {};

      if (data.name.trim() !== agent.name) {
        requestData.name = data.name.trim();
      }

      const newDescription = data.description?.trim() || null;
      if (newDescription !== (agent.description || null)) {
        requestData.description = newDescription;
      }

      if (data.llm_config_id !== agent.llm_config_id) {
        requestData.llm_config_id = data.llm_config_id;
      }

      if (data.tts_config_id !== agent.tts_config_id) {
        requestData.tts_config_id = data.tts_config_id;
      }

      if (data.stt_config_id !== agent.stt_config_id) {
        requestData.stt_config_id = data.stt_config_id;
      }

      if (data.telephony_config_id !== agent.telephony_config_id) {
        requestData.telephony_config_id = data.telephony_config_id;
      }

      if (JSON.stringify(data.tts_voice_ids) !== JSON.stringify(agent.tts_voice_ids)) {
        requestData.tts_voice_ids = data.tts_voice_ids;
      }

      // Check if TTS parameters changed
      const newTtsParams = Object.keys(builtTtsParameters).length > 0 ? builtTtsParameters : null;
      if (JSON.stringify(newTtsParams) !== JSON.stringify(agent.tts_parameters || null)) {
        requestData.tts_parameters = newTtsParams;
      }

      // Check if STT parameters changed
      const newSttParams = Object.keys(builtSttParameters).length > 0 ? builtSttParameters : null;
      if (JSON.stringify(newSttParams) !== JSON.stringify(agent.stt_parameters || null)) {
        requestData.stt_parameters = newSttParams;
      }

      if (data.system_prompt.trim() !== agent.system_prompt) {
        requestData.system_prompt = data.system_prompt.trim();
      }

      const welcomeMessage = (data.welcome_message || '').trim();
      if (welcomeMessage !== (agent.welcome_message || '')) {
        requestData.welcome_message = welcomeMessage;
      }

      // Check if conversation config changed
      if (JSON.stringify(conversationConfig) !== JSON.stringify(agent.conversation_config || null)) {
        requestData.conversation_config = conversationConfig;
      }

      if (data.status !== agent.status) {
        requestData.status = data.status;
      }

      // Check if phone numbers changed
      if (JSON.stringify(inboundNumbers) !== JSON.stringify(agent.inbound_numbers || [])) {
        requestData.inbound_numbers = inboundNumbers;
      }

      if (JSON.stringify(outboundNumbers) !== JSON.stringify(agent.outbound_numbers || [])) {
        requestData.outbound_numbers = outboundNumbers;
      }

      // Check if languages changed
      if (JSON.stringify(data.supported_languages) !== JSON.stringify(agent.supported_languages || ['en'])) {
        requestData.supported_languages = data.supported_languages;
      }

      if (data.default_language !== agent.default_language) {
        requestData.default_language = data.default_language;
      }

      // Only send request if there are changes
      if (Object.keys(requestData).length === 0) {
        notifySuccess('No changes to update');
        onOpenChange(false);
        return;
      }

      updateVoiceAgent.mutate({ agentId: agent.id, data: requestData }, { onSuccess: () => onOpenChange(false) });
      return;
    }

    const requestData: CreateVoiceAgentRequest = {
      name: data.name.trim(),
      description: data.description?.trim() || undefined,
      llm_config_id: data.llm_config_id.trim(),
      tts_config_id: data.tts_config_id.trim(),
      stt_config_id: data.stt_config_id.trim(),
      telephony_config_id: data.telephony_config_id.trim(),
      tts_voice_ids: data.tts_voice_ids,
      tts_parameters: Object.keys(builtTtsParameters).length > 0 ? builtTtsParameters : null,
      stt_parameters: Object.keys(builtSttParameters).length > 0 ? builtSttParameters : null,
      system_prompt: data.system_prompt.trim(),
      welcome_message: (data.welcome_message || '').trim(),
      conversation_config: conversationConfig,
      status: data.status,
      inbound_numbers: inboundNumbers.length > 0 ? inboundNumbers : undefined,
      outbound_numbers: outboundNumbers.length > 0 ? outboundNumbers : undefined,
      supported_languages: data.supported_languages,
      default_language: data.default_language,
    };

    createVoiceAgent.mutate(
      { data: requestData, tools: pendingTools },
      {
        onSuccess: ({ voiceAgentId, failedToolCount }) => {
          if (failedToolCount > 0) {
            notifyError(
              `Voice agent created, but ${failedToolCount} tool(s) could not be attached. Attach them from Edit.`
            );
          }
          onOpenChange(false);
          // Open the new agent when the response names it
          if (voiceAgentId) {
            navigate(`/apps/${appId}/voice-agents/${voiceAgentId}`);
          }
        },
      }
    );
  };

  // TTS and STT provider settings share one renderer; `kind` picks the provider and the state it edits
  const parameterState: Record<
    ParameterKind,
    { provider?: string; values: Record<string, unknown>; set: (key: string, value: unknown) => void }
  > = {
    tts: {
      provider: selectedTtsProvider,
      values: ttsParameters,
      set: (key, value) => setTtsParameters((prev) => ({ ...prev, [key]: value })),
    },
    stt: {
      provider: selectedSttProvider,
      values: sttParameters,
      set: (key, value) => setSttParameters((prev) => ({ ...prev, [key]: value })),
    },
  };

  const renderParameterField = (kind: ParameterKind, key: string) => {
    const { provider, values, set } = parameterState[kind];
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

  const ttsProviderConfig = selectedTtsProvider ? getProviderConfig('tts', selectedTtsProvider) : null;
  const sttProviderConfig = selectedSttProvider ? getProviderConfig('stt', selectedSttProvider) : null;
  const ttsParamGroups = ttsProviderConfig ? groupParamKeys(ttsProviderConfig.parameters) : null;
  const sttParamGroups = sttProviderConfig ? groupParamKeys(sttProviderConfig.parameters) : null;

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[760px] max-h-[calc(100vh-2rem)] max-w-4xl min-w-0 flex-col overflow-hidden lg:max-w-4xl">
        <DialogHeader className="shrink-0">
          <DialogTitle>{isEdit ? 'Edit Voice Agent' : 'Create New Voice Agent'}</DialogTitle>
          <DialogDescription>
            {isEdit ? 'Update the voice agent configuration for' : 'Create a new voice agent for'}{' '}
            {selectedApp?.app_name}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit, onInvalid)} className="flex min-h-0 flex-1 flex-col">
            <Tabs
              value={activeTab}
              onValueChange={(value) => {
                if (isFormTab(value)) setActiveTab(value);
              }}
              className="flex min-h-0 flex-1 flex-col overflow-hidden"
            >
              <TabsList className="flex w-full shrink-0 [&>button]:flex-1 [&>button]:px-2">
                <TabsTrigger value={FORM_TAB.BASIC}>Basic Info</TabsTrigger>
                <TabsTrigger value={FORM_TAB.BEHAVIOR}>Behavior</TabsTrigger>
                <TabsTrigger value={FORM_TAB.CONFIGURATIONS}>Configurations</TabsTrigger>
                <TabsTrigger value={FORM_TAB.LANGUAGES}>Languages</TabsTrigger>
                <TabsTrigger value={FORM_TAB.TOOLS}>Tools</TabsTrigger>
                <TabsTrigger value={FORM_TAB.ADVANCED}>Advanced</TabsTrigger>
                <TabsTrigger value={FORM_TAB.GUIDE}>Guide</TabsTrigger>
              </TabsList>

              <TabsContent value={FORM_TAB.BASIC} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                  <FormField
                    control={form.control}
                    name="name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          Name<span className="text-red-500">*</span>
                        </FormLabel>
                        <FormControl>
                          <Input placeholder="e.g., Customer Support Agent" maxLength={100} {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="status"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Status</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Select status" />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="inactive">Inactive (Development/Testing)</SelectItem>
                            <SelectItem value="active">Active (Ready for Production)</SelectItem>
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <FormField
                  control={form.control}
                  name="description"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Description</FormLabel>
                      <FormControl>
                        <textarea
                          rows={3}
                          maxLength={500}
                          placeholder="Describe the purpose or use case for this voice agent"
                          className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring flex min-h-[80px] w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                  <FormField
                    control={form.control}
                    name="inbound_numbers"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Inbound Phone Numbers</FormLabel>
                        <FormControl>
                          <Input placeholder="e.g., +1234567890, +9876543210" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="outbound_numbers"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Outbound Phone Numbers</FormLabel>
                        <FormControl>
                          <Input placeholder="e.g., +1234567890, +9876543210" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </TabsContent>

              <TabsContent value={FORM_TAB.CONFIGURATIONS} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
                {/* 1. Speech input (STT) */}
                <section className="space-y-4 rounded-md border p-4">
                  <div className="flex items-center gap-1.5">
                    <h4 className="text-base font-semibold tracking-tight">Speech input</h4>
                    <FieldHelp ariaLabel="About speech input">How the agent hears the caller</FieldHelp>
                  </div>
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                      <FormField
                        control={form.control}
                        name="stt_config_id"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel className="frost-text-muted">
                              Provider<span className="text-red-500">*</span>
                            </FormLabel>
                            <Select onValueChange={field.onChange} value={field.value}>
                              <FormControl>
                                <SelectTrigger>
                                  <SelectValue placeholder="Select STT configuration" />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                {sttConfigs.map((config) => (
                                  <SelectItem key={config.id} value={config.id}>
                                    {getVoiceProviderLabel('stt', config.provider)}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      {sttParamGroups?.compact.map((key) => renderParameterField('stt', key))}
                    </div>
                    {sttParamGroups && sttParamGroups.sliders.length > 0 && (
                      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                        {sttParamGroups.sliders.map((key) => renderParameterField('stt', key))}
                      </div>
                    )}
                    {sttParamGroups && sttParamGroups.booleans.length > 0 && (
                      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                        {sttParamGroups.booleans.map((key) => renderParameterField('stt', key))}
                      </div>
                    )}
                  </div>
                </section>

                {/* 2. Intelligence (LLM) */}
                <section className="space-y-4 rounded-md border p-4">
                  <div className="flex items-center gap-1.5">
                    <h4 className="text-base font-semibold tracking-tight">Intelligence</h4>
                    <FieldHelp ariaLabel="About intelligence">The model that decides what to say</FieldHelp>
                  </div>
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <FormField
                      control={form.control}
                      name="llm_config_id"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel className="frost-text-muted">
                            Provider<span className="text-red-500">*</span>
                          </FormLabel>
                          <Select onValueChange={field.onChange} value={field.value}>
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue placeholder="Select a model" />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              {llmConfigs.map((config) => (
                                <SelectItem key={config.id} value={config.id}>
                                  {config.display_name}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </section>

                {/* 3. Speech output (TTS) */}
                <section className="space-y-4 rounded-md border p-4">
                  <div className="flex items-center gap-1.5">
                    <h4 className="text-base font-semibold tracking-tight">Speech output</h4>
                    <FieldHelp ariaLabel="About speech output">How the agent speaks back</FieldHelp>
                  </div>
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                      <FormField
                        control={form.control}
                        name="tts_config_id"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel className="frost-text-muted">
                              Provider<span className="text-red-500">*</span>
                            </FormLabel>
                            <Select onValueChange={field.onChange} value={field.value}>
                              <FormControl>
                                <SelectTrigger>
                                  <SelectValue placeholder="Select TTS configuration" />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                {ttsConfigs.map((config) => (
                                  <SelectItem key={config.id} value={config.id}>
                                    {getVoiceProviderLabel('tts', config.provider)}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      {ttsParamGroups?.compact.map((key) => renderParameterField('tts', key))}
                    </div>
                    {ttsParamGroups && ttsParamGroups.sliders.length > 0 && (
                      <div className="grid grid-cols-1 gap-x-4 gap-y-8 sm:grid-cols-2">
                        {ttsParamGroups.sliders.map((key) => renderParameterField('tts', key))}
                      </div>
                    )}
                    {ttsParamGroups && ttsParamGroups.booleans.length > 0 && (
                      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                        {ttsParamGroups.booleans.map((key) => renderParameterField('tts', key))}
                      </div>
                    )}
                    {selectedTtsProvider && (
                      <FormField
                        control={form.control}
                        name="tts_voice_ids"
                        render={({ field }) => (
                          <FormItem>
                            <VoiceIdsSection
                              provider={selectedTtsProvider}
                              model={typeof ttsParameters.model === 'string' ? ttsParameters.model : undefined}
                              languages={watchedSupportedLanguages}
                              voiceIds={voiceIdState}
                              customizePerLanguage={customizeVoicesPerLanguage}
                              onCustomizePerLanguageChange={setCustomizeVoicesPerLanguage}
                              onChange={(next) => {
                                setVoiceIdState(next);
                                field.onChange(next);
                              }}
                            />
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    )}
                  </div>
                </section>

                {/* 4. Telephony */}
                <section className="space-y-4 rounded-md border p-4">
                  <div className="flex items-center gap-1.5">
                    <h4 className="text-base font-semibold tracking-tight">Telephony</h4>
                    <FieldHelp ariaLabel="About telephony">
                      Provider credentials for calls (numbers are on the Basic Info tab)
                    </FieldHelp>
                  </div>
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <FormField
                      control={form.control}
                      name="telephony_config_id"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel className="frost-text-muted">
                            Provider<span className="text-red-500">*</span>
                          </FormLabel>
                          <Select onValueChange={field.onChange} value={field.value}>
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue placeholder="Select telephony configuration" />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              {telephonyConfigs.map((config) => (
                                <SelectItem key={config.id} value={config.id}>
                                  {getTelephonyProviderConfig(config.provider as TelephonyProvider).name}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>
                </section>
              </TabsContent>

              <TabsContent value={FORM_TAB.LANGUAGES} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
                <FormField
                  control={form.control}
                  name="supported_languages"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Supported Languages<span className="text-red-500">*</span>
                      </FormLabel>
                      <div className="rounded-md border p-4">
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
                          {SUPPORTED_LANGUAGES.map((lang) => (
                            <div key={lang.code} className="flex items-center space-x-2">
                              <Checkbox
                                id={`${isEdit ? 'edit-' : ''}supported-lang-${lang.code}`}
                                checked={field.value?.includes(lang.code)}
                                onCheckedChange={(checked) => {
                                  const current = field.value || [];
                                  if (checked) {
                                    field.onChange([...current, lang.code]);
                                  } else {
                                    field.onChange(current.filter((l) => l !== lang.code));
                                  }
                                }}
                              />
                              <label
                                htmlFor={`${isEdit ? 'edit-' : ''}supported-lang-${lang.code}`}
                                className="cursor-pointer text-sm leading-none font-normal peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                              >
                                {getLanguageDisplayName(lang.code)}
                              </label>
                            </div>
                          ))}
                        </div>
                      </div>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="default_language"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Default Language<span className="text-red-500">*</span>
                      </FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select default language" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {SUPPORTED_LANGUAGES.filter((lang) =>
                            form.watch('supported_languages')?.includes(lang.code)
                          ).map((lang) => (
                            <SelectItem key={lang.code} value={lang.code}>
                              {getLanguageDisplayName(lang.code)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </TabsContent>

              <TabsContent
                value={FORM_TAB.BEHAVIOR}
                className="mt-4 flex min-h-0 flex-1 flex-col gap-4 overflow-hidden"
              >
                <FormField
                  control={form.control}
                  name="system_prompt"
                  render={({ field }) => (
                    <FormItem className="flex min-h-0 flex-[2] flex-col gap-2">
                      <FormLabel>
                        System Prompt<span className="text-red-500">*</span>
                      </FormLabel>
                      <div className="relative min-h-0 flex-1">
                        <FormControl>
                          <textarea
                            placeholder="You are a helpful customer support agent. Answer questions politely and professionally..."
                            className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring absolute inset-0 h-full w-full resize-none rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                            {...field}
                          />
                        </FormControl>
                      </div>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="welcome_message"
                  render={({ field }) => (
                    <FormItem className="flex min-h-0 flex-1 flex-col gap-2">
                      <FormLabel>Welcome Message</FormLabel>
                      <div className="relative min-h-0 flex-1">
                        <FormControl>
                          <textarea
                            placeholder="Optional. Leave blank to skip the greeting. Example: Hello! How can I help you today?"
                            className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring absolute inset-0 h-full w-full resize-none rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                            {...field}
                          />
                        </FormControl>
                      </div>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </TabsContent>

              <TabsContent value={FORM_TAB.TOOLS} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
                {agent ? (
                  <VoiceAgentToolsManager appId={appId} agentId={agent.id} />
                ) : (
                  <VoiceAgentToolsManager
                    appId={appId}
                    pendingTools={pendingTools}
                    onPendingToolsChange={setPendingTools}
                  />
                )}
              </TabsContent>

              <TabsContent value={FORM_TAB.ADVANCED} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
                <ConversationConfigField
                  form={form}
                  name="conversation_config"
                  hasWelcomeMessage={!!form.watch('welcome_message')?.trim()}
                />
              </TabsContent>

              <TabsContent value={FORM_TAB.GUIDE} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
                <ConversationConfigGuide />
              </TabsContent>
            </Tabs>

            <DialogFooter className="shrink-0 pt-4">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={saving}>
                {SUBMIT_LABEL[isEdit ? 'edit' : 'create']}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default VoiceAgentFormDialog;
