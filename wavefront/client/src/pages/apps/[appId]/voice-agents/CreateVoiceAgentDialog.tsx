import floConsoleService from '@app/api';
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
import { DEFAULT_EDITOR_TEXT, fromEditorText } from './conversation-config';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Checkbox } from '@app/components/ui/checkbox';
import { Label } from '@app/components/ui/label';
import { Slider } from '@app/components/ui/slider';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@app/components/ui/tabs';
import {
  useGetLLMConfigs,
  useGetSttConfigs,
  useGetTelephonyConfigs,
  useGetTtsConfigs,
} from '@app/hooks/data/fetch-hooks';
import { extractErrorMessage } from '@app/lib/utils';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { CreateVoiceAgentRequest } from '@app/types/voice-agent';
import { SUPPORTED_LANGUAGES, getLanguageDisplayName } from '@app/constants/languages';
import FieldHelp from '@app/components/FieldHelp';
import { VoiceIdsSection } from '@app/components/VoiceIdsSection';
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
import React, { useEffect, useState } from 'react';
import { FieldErrors, useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { z } from 'zod';

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

const createVoiceAgentSchema = z.object({
  name: z.string().min(1, 'Name is required').max(100, 'Name must be 100 characters or less'),
  description: z.string().max(500, 'Description must be 500 characters or less').optional(),
  llm_config_id: z.string().min(1, 'LLM configuration is required'),
  tts_config_id: z.string().min(1, 'TTS configuration is required'),
  stt_config_id: z.string().min(1, 'STT configuration is required'),
  telephony_config_id: z.string().min(1, 'Telephony configuration is required'),
  tts_voice_ids: z
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

type CreateVoiceAgentInput = z.infer<typeof createVoiceAgentSchema>;

const FIELD_TAB_MAP: Record<keyof CreateVoiceAgentInput, FormTab> = {
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

interface CreateVoiceAgentDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  onSuccess?: () => void;
}

const CreateVoiceAgentDialog: React.FC<CreateVoiceAgentDialogProps> = ({ isOpen, onOpenChange, appId, onSuccess }) => {
  const navigate = useNavigate();
  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();
  const [creating, setCreating] = useState(false);
  const [activeTab, setActiveTab] = useState<FormTab>(FORM_TAB.BASIC);
  const [ttsParameters, setTtsParameters] = useState<Record<string, unknown>>({});
  const [sttParameters, setSttParameters] = useState<Record<string, unknown>>({});
  const [voiceIdState, setVoiceIdState] = useState<Record<string, string>>({ en: '' });
  const [customizeVoicesPerLanguage, setCustomizeVoicesPerLanguage] = useState(false);
  const [pendingTools, setPendingTools] = useState<PendingAgentTool[]>([]);

  // Fetch configs for dropdowns
  const { data: llmConfigs = [] } = useGetLLMConfigs(appId);
  const { data: ttsConfigs = [] } = useGetTtsConfigs(appId);
  const { data: sttConfigs = [] } = useGetSttConfigs(appId);
  const { data: telephonyConfigs = [] } = useGetTelephonyConfigs(appId);

  const form = useForm<CreateVoiceAgentInput>({
    resolver: zodResolver(createVoiceAgentSchema),
    defaultValues: {
      name: '',
      description: '',
      llm_config_id: '',
      tts_config_id: '',
      stt_config_id: '',
      telephony_config_id: '',
      tts_voice_ids: { en: '' },
      system_prompt: '',
      welcome_message: '',
      conversation_config: DEFAULT_EDITOR_TEXT,
      status: 'inactive',
      inbound_numbers: '',
      outbound_numbers: '',
      supported_languages: ['en'],
      default_language: 'en',
    },
  });

  // Watch config selections to determine providers
  const watchedTtsConfigId = form.watch('tts_config_id');
  const watchedSttConfigId = form.watch('stt_config_id');
  const watchedSupportedLanguages = form.watch('supported_languages');

  // Get selected providers
  const selectedTtsProvider = ttsConfigs.find((c) => c.id === watchedTtsConfigId)?.provider;
  const selectedSttProvider = sttConfigs.find((c) => c.id === watchedSttConfigId)?.provider;

  // Initialize parameters when provider changes
  useEffect(() => {
    if (isOpen && selectedTtsProvider) {
      setTtsParameters(initializeParameters('tts', selectedTtsProvider));
    }
  }, [selectedTtsProvider, isOpen]);

  useEffect(() => {
    if (isOpen && selectedSttProvider) {
      setSttParameters(initializeParameters('stt', selectedSttProvider));
    }
  }, [selectedSttProvider, isOpen]);

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
  }, [watchedSupportedLanguages, isOpen, customizeVoicesPerLanguage]);

  // Reset form when dialog closes
  useEffect(() => {
    if (!isOpen) {
      form.reset({
        name: '',
        description: '',
        llm_config_id: '',
        tts_config_id: '',
        stt_config_id: '',
        telephony_config_id: '',
        tts_voice_ids: { en: '' },
        system_prompt: '',
        welcome_message: '',
        conversation_config: DEFAULT_EDITOR_TEXT,
        status: 'inactive',
        inbound_numbers: '',
        outbound_numbers: '',
        supported_languages: ['en'],
        default_language: 'en',
      });
      setTtsParameters({});
      setSttParameters({});
      setVoiceIdState({ en: '' });
      setCustomizeVoicesPerLanguage(false);
      setPendingTools([]);
      setActiveTab(FORM_TAB.BASIC);
    }
  }, [isOpen, form]);

  const onInvalid = (errors: FieldErrors<CreateVoiceAgentInput>) => {
    const firstErrorField = Object.keys(errors)[0] as keyof CreateVoiceAgentInput | undefined;
    if (firstErrorField && FIELD_TAB_MAP[firstErrorField]) {
      setActiveTab(FIELD_TAB_MAP[firstErrorField]);
    }
  };

  const onSubmit = async (data: CreateVoiceAgentInput) => {
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

    setCreating(true);
    try {
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

      const response = await floConsoleService.voiceAgentService.createVoiceAgent(requestData);

      if (response.data?.meta?.status === 'success') {
        const agentId = response.data?.data?.voice_agent_id;
        if (agentId && pendingTools.length > 0) {
          const results = await Promise.allSettled(
            pendingTools.map(({ toolId, isEnabled }) =>
              floConsoleService.toolService.attachToolToAgent(agentId, {
                tool_id: toolId,
                is_enabled: isEnabled,
                priority: 0,
              })
            )
          );
          const failed = results.filter((r) => r.status === 'rejected').length;
          if (failed > 0) {
            notifyError(`Voice agent created, but ${failed} tool(s) could not be attached. Attach them from Edit.`);
          }
        }
        notifySuccess('Voice agent created successfully');

        if (onSuccess) {
          onSuccess();
        }

        onOpenChange(false);

        // Optionally navigate to the created agent if we have the ID
        if (response.data?.data?.voice_agent_id) {
          navigate(`/apps/${appId}/voice-agents/${response.data.data.voice_agent_id}`);
        }
      }
    } catch (error) {
      console.error('Error creating voice agent:', error);
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to create voice agent');
    } finally {
      setCreating(false);
    }
  };

  // Helper functions for parameter management
  const setTtsParameter = (key: string, value: unknown) => {
    setTtsParameters((prev) => ({ ...prev, [key]: value }));
  };

  const setSttParameter = (key: string, value: unknown) => {
    setSttParameters((prev) => ({ ...prev, [key]: value }));
  };

  // Render TTS parameter field
  const renderTtsParameterField = (key: string) => {
    if (!selectedTtsProvider) return null;
    const config = getProviderConfig('tts', selectedTtsProvider);
    if (!config) return null;

    const paramConfig = config.parameters[key];
    if (!paramConfig) return null;

    switch (paramConfig.type) {
      case 'boolean':
        return (
          <div key={key} className="flex items-center space-x-2">
            <Checkbox
              id={`tts-${key}`}
              checked={getBooleanParameterWithDefault(ttsParameters, key, paramConfig.default)}
              onCheckedChange={(checked) => setTtsParameter(key, checked)}
            />
            <Label htmlFor={`tts-${key}`} className="frost-text-muted cursor-pointer">
              {paramConfig.description || key}
            </Label>
          </div>
        );

      case 'number':
        if (paramConfig.min !== undefined && paramConfig.max !== undefined) {
          const sliderValue = getNumberParameterWithDefault(ttsParameters, key, paramConfig.default, paramConfig.min);
          return (
            <div key={key} className="space-y-2">
              <Label className="frost-text-muted">
                {paramConfig.description || key}: {sliderValue.toFixed(2)}
              </Label>
              <Slider
                min={paramConfig.min}
                max={paramConfig.max}
                step={paramConfig.step || 1}
                value={[sliderValue]}
                onValueChange={(values: number[]) => setTtsParameter(key, values[0])}
              />
            </div>
          );
        }

        return (
          <div key={key} className="space-y-2">
            <Label className="frost-text-muted">{paramConfig.description || key}</Label>
            <Input
              type="number"
              value={getNumberOrStringParameter(ttsParameters, key)}
              onChange={(e) => setTtsParameter(key, e.target.value ? parseFloat(e.target.value) : undefined)}
              placeholder={paramConfig.placeholder}
              step={paramConfig.step}
            />
            {paramConfig.placeholder && (
              <p className="text-muted-foreground text-[0.8rem]">e.g., {paramConfig.placeholder}</p>
            )}
          </div>
        );

      case 'string':
      default:
        if (key === 'language') return null;

        if (paramConfig.options && paramConfig.options.length > 0) {
          const current = getStringParameter(ttsParameters, key);
          const selectValue =
            current ||
            (paramConfig.default !== undefined && paramConfig.default !== '' ? String(paramConfig.default) : undefined);
          return (
            <div key={key} className="space-y-2">
              <Label className="frost-text-muted">{paramConfig.description || key}</Label>
              <Select value={selectValue} onValueChange={(val) => setTtsParameter(key, val)}>
                <SelectTrigger>
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
            <Label className="frost-text-muted">{paramConfig.description || key}</Label>
            <Input
              type="text"
              value={getStringParameter(ttsParameters, key)}
              onChange={(e) => setTtsParameter(key, e.target.value)}
              placeholder={paramConfig.placeholder}
            />
            {paramConfig.placeholder && (
              <p className="text-muted-foreground text-[0.8rem]">Default: {paramConfig.placeholder}</p>
            )}
          </div>
        );
    }
  };

  // Render STT parameter field
  const renderSttParameterField = (key: string) => {
    if (!selectedSttProvider) return null;
    const config = getProviderConfig('stt', selectedSttProvider);
    if (!config) return null;

    const paramConfig = config.parameters[key];
    if (!paramConfig) return null;

    switch (paramConfig.type) {
      case 'boolean':
        return (
          <div key={key} className="flex items-center space-x-2">
            <Checkbox
              id={`stt-${key}`}
              checked={getBooleanParameterWithDefault(sttParameters, key, paramConfig.default)}
              onCheckedChange={(checked) => setSttParameter(key, checked)}
            />
            <Label htmlFor={`stt-${key}`} className="frost-text-muted cursor-pointer">
              {paramConfig.description || key}
            </Label>
          </div>
        );

      case 'number':
        if (paramConfig.min !== undefined && paramConfig.max !== undefined) {
          const sliderValue = getNumberParameterWithDefault(sttParameters, key, paramConfig.default, paramConfig.min);
          return (
            <div key={key} className="space-y-2">
              <Label className="frost-text-muted">
                {paramConfig.description || key}: {sliderValue}
              </Label>
              <Slider
                min={paramConfig.min}
                max={paramConfig.max}
                step={paramConfig.step || 1}
                value={[sliderValue]}
                onValueChange={(values: number[]) => setSttParameter(key, values[0])}
              />
            </div>
          );
        }

        return (
          <div key={key} className="space-y-2">
            <Label className="frost-text-muted">{paramConfig.description || key}</Label>
            <Input
              type="number"
              value={getNumberOrStringParameter(sttParameters, key)}
              onChange={(e) => setSttParameter(key, e.target.value ? parseInt(e.target.value) : undefined)}
              placeholder={paramConfig.placeholder}
            />
            {paramConfig.placeholder && (
              <p className="text-muted-foreground text-[0.8rem]">e.g., {paramConfig.placeholder}</p>
            )}
          </div>
        );

      case 'string':
      default:
        if (key === 'language') return null;

        if (paramConfig.options && paramConfig.options.length > 0) {
          const current = getStringParameter(sttParameters, key);
          const selectValue =
            current ||
            (paramConfig.default !== undefined && paramConfig.default !== '' ? String(paramConfig.default) : undefined);
          return (
            <div key={key} className="space-y-2">
              <Label className="frost-text-muted">{paramConfig.description || key}</Label>
              <Select value={selectValue} onValueChange={(val) => setSttParameter(key, val)}>
                <SelectTrigger>
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
            <Label className="frost-text-muted">{paramConfig.description || key}</Label>
            <Input
              type="text"
              value={getStringParameter(sttParameters, key)}
              onChange={(e) => setSttParameter(key, e.target.value)}
              placeholder={paramConfig.placeholder}
            />
            {paramConfig.placeholder && (
              <p className="text-muted-foreground text-[0.8rem]">Default: {paramConfig.placeholder}</p>
            )}
          </div>
        );
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
          <DialogTitle>Create New Voice Agent</DialogTitle>
          <DialogDescription>Create a new voice agent for {selectedApp?.app_name}</DialogDescription>
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
                      {sttParamGroups?.compact.map((key) => renderSttParameterField(key))}
                    </div>
                    {sttParamGroups && sttParamGroups.sliders.length > 0 && (
                      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                        {sttParamGroups.sliders.map((key) => renderSttParameterField(key))}
                      </div>
                    )}
                    {sttParamGroups && sttParamGroups.booleans.length > 0 && (
                      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                        {sttParamGroups.booleans.map((key) => renderSttParameterField(key))}
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
                                <SelectValue placeholder="Select LLM configuration" />
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
                      {ttsParamGroups?.compact.map((key) => renderTtsParameterField(key))}
                    </div>
                    {ttsParamGroups && ttsParamGroups.sliders.length > 0 && (
                      <div className="grid grid-cols-1 gap-x-4 gap-y-8 sm:grid-cols-2">
                        {ttsParamGroups.sliders.map((key) => renderTtsParameterField(key))}
                      </div>
                    )}
                    {ttsParamGroups && ttsParamGroups.booleans.length > 0 && (
                      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                        {ttsParamGroups.booleans.map((key) => renderTtsParameterField(key))}
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
                                id={`supported-lang-${lang.code}`}
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
                                htmlFor={`supported-lang-${lang.code}`}
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
                <VoiceAgentToolsManager
                  appId={appId}
                  pendingTools={pendingTools}
                  onPendingToolsChange={setPendingTools}
                />
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
              <Button type="submit" loading={creating || form.formState.isSubmitting}>
                Create Voice Agent
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateVoiceAgentDialog;
