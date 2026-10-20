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
import VoiceAgentToolsManager from './VoiceAgentToolsManager';
import ConversationConfigField from './ConversationConfigField';
import { fromEditorText, toEditorText } from './conversation-config';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Label } from '@app/components/ui/label';
import { Slider } from '@app/components/ui/slider';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Checkbox } from '@app/components/ui/checkbox';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@app/components/ui/tabs';
import {
  useGetLLMConfigs,
  useGetSttConfigs,
  useGetTelephonyConfigs,
  useGetTtsConfigs,
} from '@app/hooks/data/fetch-hooks';
import { extractErrorMessage } from '@app/lib/utils';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { UpdateVoiceAgentRequest, VoiceAgent } from '@app/types/voice-agent';
import FieldHelp from '@app/components/FieldHelp';
import { VoiceIdsSection } from '@app/components/VoiceIdsSection';
import { SUPPORTED_LANGUAGES, getLanguageDisplayName } from '@app/constants/languages';
import { getTelephonyProviderConfig } from '@app/config/telephony-providers';
import { getProviderConfig, getVoiceProviderLabel, groupParamKeys } from '@app/config/voice-providers';
import { TelephonyProvider } from '@app/types/telephony-config';
import { getBooleanParameterWithDefault, getNumberParameterWithDefault } from '@app/utils/parameter-helpers';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useState } from 'react';
import { FieldErrors, useForm } from 'react-hook-form';
import { z } from 'zod';

const E164_REGEX = /^\+[1-9]\d{1,14}$/;

const FORM_TAB = {
  BASIC: 'basic',
  CONFIGURATIONS: 'configurations',
  PHONE_NUMBERS: 'phone-numbers',
  LANGUAGES: 'languages',
  BEHAVIOR: 'behavior',
  ADVANCED: 'advanced',
  TOOLS: 'tools',
} as const;

type FormTab = (typeof FORM_TAB)[keyof typeof FORM_TAB];

const isFormTab = (value: string): value is FormTab => Object.values(FORM_TAB).includes(value as FormTab);

const updateVoiceAgentSchema = z.object({
  name: z.string().min(1, 'Name is required').max(100, 'Name must be 100 characters or less'),
  description: z.string().max(500, 'Description must be 500 characters or less').optional(),
  llm_config_id: z.string().min(1, 'LLM configuration is required'),
  tts_config_id: z.string().min(1, 'TTS configuration is required'),
  stt_config_id: z.string().min(1, 'STT configuration is required'),
  telephony_config_id: z.string().min(1, 'Telephony configuration is required'),
  tts_voice_ids: z.record(z.string(), z.string()).optional(),
  system_prompt: z.string().min(1, 'System prompt is required'),
  welcome_message: z.string(),
  conversation_config: z.string().optional(),
  status: z.enum(['active', 'inactive']),
  inbound_numbers: z.string().optional(),
  outbound_numbers: z.string().optional(),
  supported_languages: z.array(z.string()).min(1, 'At least one language is required'),
  default_language: z.string().min(1, 'Default language is required'),
});

type UpdateVoiceAgentInput = z.infer<typeof updateVoiceAgentSchema>;

const FIELD_TAB_MAP: Record<keyof UpdateVoiceAgentInput, FormTab> = {
  name: FORM_TAB.BASIC,
  description: FORM_TAB.BASIC,
  status: FORM_TAB.BASIC,
  llm_config_id: FORM_TAB.CONFIGURATIONS,
  tts_config_id: FORM_TAB.CONFIGURATIONS,
  stt_config_id: FORM_TAB.CONFIGURATIONS,
  telephony_config_id: FORM_TAB.CONFIGURATIONS,
  tts_voice_ids: FORM_TAB.CONFIGURATIONS,
  inbound_numbers: FORM_TAB.PHONE_NUMBERS,
  outbound_numbers: FORM_TAB.PHONE_NUMBERS,
  supported_languages: FORM_TAB.LANGUAGES,
  default_language: FORM_TAB.LANGUAGES,
  system_prompt: FORM_TAB.BEHAVIOR,
  welcome_message: FORM_TAB.BEHAVIOR,
  conversation_config: FORM_TAB.ADVANCED,
};

interface EditVoiceAgentDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  agent: VoiceAgent;
  onSuccess?: () => void;
}

const EditVoiceAgentDialog: React.FC<EditVoiceAgentDialogProps> = ({
  isOpen,
  onOpenChange,
  appId,
  agent,
  onSuccess,
}) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();
  const [updating, setUpdating] = useState(false);
  const [activeTab, setActiveTab] = useState<FormTab>(FORM_TAB.BASIC);

  // Fetch configs for dropdowns
  const { data: llmConfigs = [] } = useGetLLMConfigs(appId);
  const { data: ttsConfigs = [] } = useGetTtsConfigs(appId);
  const { data: sttConfigs = [] } = useGetSttConfigs(appId);
  const { data: telephonyConfigs = [] } = useGetTelephonyConfigs(appId);

  // State for TTS/STT parameters (managed separately from form)
  const [ttsParameters, setTtsParameters] = useState<Record<string, unknown>>({});
  const [sttParameters, setSttParameters] = useState<Record<string, unknown>>({});
  const [voiceIdState, setVoiceIdState] = useState<Record<string, string>>(agent.tts_voice_ids || { en: '' });
  const [customizeVoicesPerLanguage, setCustomizeVoicesPerLanguage] = useState(() => {
    const ids = Object.values(agent.tts_voice_ids || {});
    return ids.length > 1 && new Set(ids).size > 1;
  });

  const form = useForm<UpdateVoiceAgentInput>({
    resolver: zodResolver(updateVoiceAgentSchema),
    defaultValues: {
      name: agent.name,
      description: agent.description || '',
      llm_config_id: agent.llm_config_id,
      tts_config_id: agent.tts_config_id,
      stt_config_id: agent.stt_config_id,
      telephony_config_id: agent.telephony_config_id,
      tts_voice_ids: agent.tts_voice_ids,
      system_prompt: agent.system_prompt,
      welcome_message: agent.welcome_message,
      conversation_config: toEditorText(agent.conversation_config),
      status: agent.status,
      inbound_numbers: agent.inbound_numbers?.join(', ') || '',
      outbound_numbers: agent.outbound_numbers?.join(', ') || '',
      supported_languages: agent.supported_languages || ['en'],
      default_language: agent.default_language || 'en',
    },
  });

  // Watch for config changes to determine providers
  const watchedTtsConfigId = form.watch('tts_config_id');
  const watchedSttConfigId = form.watch('stt_config_id');
  const watchedSupportedLanguages = form.watch('supported_languages');

  const selectedTtsProvider = ttsConfigs.find((c) => c.id === watchedTtsConfigId)?.provider;
  const selectedSttProvider = sttConfigs.find((c) => c.id === watchedSttConfigId)?.provider;

  const ttsProviderConfig = selectedTtsProvider ? getProviderConfig('tts', selectedTtsProvider) : null;
  const sttProviderConfig = selectedSttProvider ? getProviderConfig('stt', selectedSttProvider) : null;
  const ttsParamGroups = ttsProviderConfig ? groupParamKeys(ttsProviderConfig.parameters) : null;
  const sttParamGroups = sttProviderConfig ? groupParamKeys(sttProviderConfig.parameters) : null;

  // Reset form when dialog opens with agent data
  useEffect(() => {
    if (isOpen && agent) {
      form.reset({
        name: agent.name,
        description: agent.description || '',
        llm_config_id: agent.llm_config_id,
        tts_config_id: agent.tts_config_id,
        stt_config_id: agent.stt_config_id,
        telephony_config_id: agent.telephony_config_id,
        tts_voice_ids: agent.tts_voice_ids,
        system_prompt: agent.system_prompt,
        welcome_message: agent.welcome_message,
        conversation_config: toEditorText(agent.conversation_config),
        status: agent.status,
        inbound_numbers: agent.inbound_numbers?.join(', ') || '',
        outbound_numbers: agent.outbound_numbers?.join(', ') || '',
        supported_languages: agent.supported_languages || ['en'],
        default_language: agent.default_language || 'en',
      });
      setVoiceIdState(agent.tts_voice_ids || { en: '' });
      const ids = Object.values(agent.tts_voice_ids || {});
      setCustomizeVoicesPerLanguage(ids.length > 1 && new Set(ids).size > 1);
      setActiveTab(FORM_TAB.BASIC);
    }
  }, [isOpen, agent, form]);

  // Initialize TTS parameters when dialog opens - use only existing values, not merged with defaults
  useEffect(() => {
    if (isOpen) {
      setTtsParameters(agent.tts_parameters || {});
    }
  }, [isOpen, agent.tts_parameters]);

  // Initialize STT parameters when dialog opens - use only existing values, not merged with defaults
  useEffect(() => {
    if (isOpen) {
      setSttParameters(agent.stt_parameters || {});
    }
  }, [isOpen, agent.stt_parameters]);

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

  // Helper functions to update parameters
  const setTtsParameter = (key: string, value: unknown) => {
    setTtsParameters((prev) => ({ ...prev, [key]: value }));
  };

  const setSttParameter = (key: string, value: unknown) => {
    setSttParameters((prev) => ({ ...prev, [key]: value }));
  };

  const onInvalid = (errors: FieldErrors<UpdateVoiceAgentInput>) => {
    const firstErrorField = Object.keys(errors)[0] as keyof UpdateVoiceAgentInput | undefined;
    if (firstErrorField && FIELD_TAB_MAP[firstErrorField]) {
      setActiveTab(FIELD_TAB_MAP[firstErrorField]);
    }
  };

  const onSubmit = async (data: UpdateVoiceAgentInput) => {
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

    setUpdating(true);
    try {
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

      await floConsoleService.voiceAgentService.updateVoiceAgent(agent.id, requestData);

      notifySuccess('Voice agent updated successfully');

      if (onSuccess) {
        onSuccess();
      }

      onOpenChange(false);
    } catch (error) {
      console.error('Error updating voice agent:', error);
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to update voice agent');
    } finally {
      setUpdating(false);
    }
  };

  // Render TTS parameter field based on type
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
        // Number without range - use input
        return (
          <div key={key} className="space-y-2">
            <Label htmlFor={`tts-${key}`} className="frost-text-muted">
              {paramConfig.description || key}
            </Label>
            <Input
              id={`tts-${key}`}
              type="number"
              value={(ttsParameters[key] ?? paramConfig.default ?? 0) as number}
              onChange={(e) => setTtsParameter(key, parseFloat(e.target.value) || 0)}
            />
          </div>
        );

      case 'string':
        if (paramConfig.options && paramConfig.options.length > 0) {
          const raw = ttsParameters[key] ?? paramConfig.default;
          const currentValue = raw !== undefined && raw !== '' ? String(raw) : undefined;
          return (
            <div key={key} className="space-y-2">
              <Label htmlFor={`tts-${key}`} className="frost-text-muted">
                {paramConfig.description || key}
              </Label>
              <Select value={currentValue} onValueChange={(value) => setTtsParameter(key, value)}>
                <SelectTrigger id={`tts-${key}`}>
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                  {paramConfig.options.map((opt) => (
                    <SelectItem key={String(opt)} value={String(opt)}>
                      {opt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          );
        }
        // Text input for free-form strings
        return (
          <div key={key} className="space-y-2">
            <Label htmlFor={`tts-${key}`} className="frost-text-muted">
              {paramConfig.description || key}
            </Label>
            <Input
              id={`tts-${key}`}
              type="text"
              value={String(ttsParameters[key] ?? paramConfig.default ?? '')}
              onChange={(e) => setTtsParameter(key, e.target.value)}
            />
          </div>
        );

      default:
        return null;
    }
  };

  // Render STT parameter field based on type
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
                {paramConfig.description || key}: {sliderValue.toFixed(2)}
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
        // Number without range - use input
        return (
          <div key={key} className="space-y-2">
            <Label htmlFor={`stt-${key}`} className="frost-text-muted">
              {paramConfig.description || key}
            </Label>
            <Input
              id={`stt-${key}`}
              type="number"
              value={(sttParameters[key] ?? paramConfig.default ?? 0) as number}
              onChange={(e) => setSttParameter(key, parseFloat(e.target.value) || 0)}
            />
          </div>
        );

      case 'string':
        if (paramConfig.options && paramConfig.options.length > 0) {
          const raw = sttParameters[key] ?? paramConfig.default;
          const currentValue = raw !== undefined && raw !== '' ? String(raw) : undefined;
          return (
            <div key={key} className="space-y-2">
              <Label htmlFor={`stt-${key}`} className="frost-text-muted">
                {paramConfig.description || key}
              </Label>
              <Select value={currentValue} onValueChange={(value) => setSttParameter(key, value)}>
                <SelectTrigger id={`stt-${key}`}>
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                  {paramConfig.options.map((opt) => (
                    <SelectItem key={String(opt)} value={String(opt)}>
                      {opt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          );
        }
        // Text input for free-form strings
        return (
          <div key={key} className="space-y-2">
            <Label htmlFor={`stt-${key}`} className="frost-text-muted">
              {paramConfig.description || key}
            </Label>
            <Input
              id={`stt-${key}`}
              type="text"
              value={String(sttParameters[key] ?? paramConfig.default ?? '')}
              onChange={(e) => setSttParameter(key, e.target.value)}
            />
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[760px] max-h-[calc(100vh-2rem)] max-w-4xl min-w-0 flex-col overflow-hidden lg:max-w-4xl">
        <DialogHeader className="shrink-0">
          <DialogTitle>Edit Voice Agent</DialogTitle>
          <DialogDescription>Update the voice agent configuration for {selectedApp?.app_name}</DialogDescription>
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
              <TabsList className="grid w-full shrink-0 grid-cols-7">
                <TabsTrigger value={FORM_TAB.BASIC}>Basic Info</TabsTrigger>
                <TabsTrigger value={FORM_TAB.BEHAVIOR}>Behavior</TabsTrigger>
                <TabsTrigger value={FORM_TAB.CONFIGURATIONS}>Configurations</TabsTrigger>
                <TabsTrigger value={FORM_TAB.PHONE_NUMBERS}>Phone Numbers</TabsTrigger>
                <TabsTrigger value={FORM_TAB.LANGUAGES}>Languages</TabsTrigger>
                <TabsTrigger value={FORM_TAB.ADVANCED}>Advanced</TabsTrigger>
                <TabsTrigger value={FORM_TAB.TOOLS}>Tools</TabsTrigger>
              </TabsList>

              <TabsContent value={FORM_TAB.BASIC} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
                <div className="grid grid-cols-2 gap-6">
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
              </TabsContent>

              <TabsContent value={FORM_TAB.CONFIGURATIONS} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
                {/* 1. Speech input (STT) */}
                <section className="space-y-4 rounded-md border p-4">
                  <div className="flex items-center gap-1.5">
                    <h4 className="text-base font-semibold tracking-tight">Speech input</h4>
                    <FieldHelp ariaLabel="About speech input">How the agent hears the caller</FieldHelp>
                  </div>
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
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
                      <div className="grid grid-cols-2 gap-4">
                        {sttParamGroups.sliders.map((key) => renderSttParameterField(key))}
                      </div>
                    )}
                    {sttParamGroups && sttParamGroups.booleans.length > 0 && (
                      <div className="grid grid-cols-2 gap-4">
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
                  <div className="grid grid-cols-2 gap-4">
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
                    <div className="grid grid-cols-2 gap-4">
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
                      <div className="grid grid-cols-2 gap-4">
                        {ttsParamGroups.sliders.map((key) => renderTtsParameterField(key))}
                      </div>
                    )}
                    {ttsParamGroups && ttsParamGroups.booleans.length > 0 && (
                      <div className="grid grid-cols-2 gap-4">
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
                      Provider credentials for calls (numbers are on the Phone Numbers tab)
                    </FieldHelp>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
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

              <TabsContent value={FORM_TAB.PHONE_NUMBERS} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
                <div className="grid grid-cols-1 gap-6">
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
                        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
                          {SUPPORTED_LANGUAGES.map((lang) => (
                            <div key={lang.code} className="flex items-center space-x-2">
                              <Checkbox
                                id={`edit-supported-lang-${lang.code}`}
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
                                htmlFor={`edit-supported-lang-${lang.code}`}
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

              <TabsContent value={FORM_TAB.ADVANCED} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
                <ConversationConfigField form={form} name="conversation_config" />
              </TabsContent>

              <TabsContent value={FORM_TAB.TOOLS} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
                <VoiceAgentToolsManager appId={appId} agentId={agent.id} />
              </TabsContent>
            </Tabs>

            <DialogFooter className="shrink-0 pt-4">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={updating || form.formState.isSubmitting}>
                Update Voice Agent
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default EditVoiceAgentDialog;
