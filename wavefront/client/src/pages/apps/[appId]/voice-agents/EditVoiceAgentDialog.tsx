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
import { Label } from '@app/components/ui/label';
import { Slider } from '@app/components/ui/slider';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Checkbox } from '@app/components/ui/checkbox';
import {
  useGetLLMConfigs,
  useGetSttConfigs,
  useGetTelephonyConfigs,
  useGetTtsConfigs,
} from '@app/hooks/data/fetch-hooks';
import { extractErrorMessage } from '@app/lib/utils';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { UpdateVoiceAgentRequest, VoiceAgent } from '@app/types/voice-agent';
import { SUPPORTED_LANGUAGES, getLanguageDisplayName } from '@app/constants/languages';
import { getProviderConfig } from '@app/config/voice-providers';
import { getBooleanParameterWithDefault, getNumberParameterWithDefault } from '@app/utils/parameter-helpers';
import { zodResolver } from '@hookform/resolvers/zod';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const E164_REGEX = /^\+[1-9]\d{1,14}$/;

const updateVoiceAgentSchema = z.object({
  name: z.string().min(1, 'Name is required').max(100, 'Name must be 100 characters or less'),
  description: z.string().max(500, 'Description must be 500 characters or less').optional(),
  llm_config_id: z.string().min(1, 'LLM configuration is required'),
  tts_config_id: z.string().min(1, 'TTS configuration is required'),
  stt_config_id: z.string().min(1, 'STT configuration is required'),
  telephony_config_id: z.string().min(1, 'Telephony configuration is required'),
  tts_voice_id: z.string().min(1, 'TTS Voice ID is required'),
  system_prompt: z.string().min(1, 'System prompt is required'),
  welcome_message: z.string().min(1, 'Welcome message is required'),
  conversation_config: z.string().optional(),
  status: z.enum(['active', 'inactive']),
  inbound_numbers: z.string().optional(),
  outbound_numbers: z.string().optional(),
  supported_languages: z.array(z.string()).min(1, 'At least one language is required'),
  default_language: z.string().min(1, 'Default language is required'),
});

type UpdateVoiceAgentInput = z.infer<typeof updateVoiceAgentSchema>;

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

  // Fetch configs for dropdowns
  const { data: llmConfigs = [] } = useGetLLMConfigs(appId);
  const { data: ttsConfigs = [] } = useGetTtsConfigs(appId);
  const { data: sttConfigs = [] } = useGetSttConfigs(appId);
  const { data: telephonyConfigs = [] } = useGetTelephonyConfigs(appId);

  // State for TTS/STT parameters (managed separately from form)
  const [ttsParameters, setTtsParameters] = useState<Record<string, unknown>>({});
  const [sttParameters, setSttParameters] = useState<Record<string, unknown>>({});

  const form = useForm<UpdateVoiceAgentInput>({
    resolver: zodResolver(updateVoiceAgentSchema),
    defaultValues: {
      name: agent.name,
      description: agent.description || '',
      llm_config_id: agent.llm_config_id,
      tts_config_id: agent.tts_config_id,
      stt_config_id: agent.stt_config_id,
      telephony_config_id: agent.telephony_config_id,
      tts_voice_id: agent.tts_voice_id,
      system_prompt: agent.system_prompt,
      welcome_message: agent.welcome_message,
      conversation_config: agent.conversation_config ? JSON.stringify(agent.conversation_config, null, 2) : '{}',
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

  const selectedTtsProvider = ttsConfigs.find((c) => c.id === watchedTtsConfigId)?.provider;
  const selectedSttProvider = sttConfigs.find((c) => c.id === watchedSttConfigId)?.provider;

  const ttsProviderConfig = selectedTtsProvider ? getProviderConfig('tts', selectedTtsProvider) : null;
  const sttProviderConfig = selectedSttProvider ? getProviderConfig('stt', selectedSttProvider) : null;

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
        tts_voice_id: agent.tts_voice_id,
        system_prompt: agent.system_prompt,
        welcome_message: agent.welcome_message,
        conversation_config: agent.conversation_config ? JSON.stringify(agent.conversation_config, null, 2) : '{}',
        status: agent.status,
        inbound_numbers: agent.inbound_numbers?.join(', ') || '',
        outbound_numbers: agent.outbound_numbers?.join(', ') || '',
        supported_languages: agent.supported_languages || ['en'],
        default_language: agent.default_language || 'en',
      });
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

  // Helper functions to update parameters
  const setTtsParameter = (key: string, value: unknown) => {
    setTtsParameters((prev) => ({ ...prev, [key]: value }));
  };

  const setSttParameter = (key: string, value: unknown) => {
    setSttParameters((prev) => ({ ...prev, [key]: value }));
  };

  const onSubmit = async (data: UpdateVoiceAgentInput) => {
    // Validate JSON if provided
    let conversationConfig = null;
    if (data.conversation_config?.trim() && data.conversation_config.trim() !== '{}') {
      try {
        conversationConfig = JSON.parse(data.conversation_config);
      } catch {
        notifyError('Invalid JSON in conversation configuration');
        return;
      }
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

      if (data.tts_voice_id.trim() !== agent.tts_voice_id) {
        requestData.tts_voice_id = data.tts_voice_id.trim();
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

      if (data.welcome_message.trim() !== agent.welcome_message) {
        requestData.welcome_message = data.welcome_message.trim();
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
          <div key={key} className="col-span-2">
            <div className="flex items-center space-x-2">
              <Checkbox
                id={`tts-${key}`}
                checked={getBooleanParameterWithDefault(ttsParameters, key, paramConfig.default)}
                onCheckedChange={(checked) => setTtsParameter(key, checked)}
              />
              <Label htmlFor={`tts-${key}`} className="cursor-pointer">
                {paramConfig.description || key}
              </Label>
            </div>
          </div>
        );

      case 'number':
        if (paramConfig.min !== undefined && paramConfig.max !== undefined) {
          const sliderValue = getNumberParameterWithDefault(ttsParameters, key, paramConfig.default, paramConfig.min);
          return (
            <div key={key} className="col-span-2 space-y-2">
              <Label>
                {paramConfig.description || key}: {sliderValue.toFixed(2)}
              </Label>
              <Slider
                min={paramConfig.min}
                max={paramConfig.max}
                step={paramConfig.step || 1}
                value={[sliderValue]}
                onValueChange={(values: number[]) => setTtsParameter(key, values[0])}
              />
              <p className="text-muted-foreground text-[0.8rem]">
                {paramConfig.min} - {paramConfig.max}
              </p>
            </div>
          );
        }
        // Number without range - use input
        return (
          <div key={key} className="col-span-2 space-y-2">
            <Label htmlFor={`tts-${key}`}>{paramConfig.description || key}</Label>
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
          // Dropdown for predefined options
          const currentValue = String(ttsParameters[key] ?? paramConfig.default ?? '');
          return (
            <div key={key} className="col-span-2 space-y-2">
              <Label htmlFor={`tts-${key}`}>{paramConfig.description || key}</Label>
              <Select value={currentValue} onValueChange={(value) => setTtsParameter(key, value)}>
                <SelectTrigger id={`tts-${key}`}>
                  <SelectValue />
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
          <div key={key} className="col-span-2 space-y-2">
            <Label htmlFor={`tts-${key}`}>{paramConfig.description || key}</Label>
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
          <div key={key} className="col-span-2">
            <div className="flex items-center space-x-2">
              <Checkbox
                id={`stt-${key}`}
                checked={getBooleanParameterWithDefault(sttParameters, key, paramConfig.default)}
                onCheckedChange={(checked) => setSttParameter(key, checked)}
              />
              <Label htmlFor={`stt-${key}`} className="cursor-pointer">
                {paramConfig.description || key}
              </Label>
            </div>
          </div>
        );

      case 'number':
        if (paramConfig.min !== undefined && paramConfig.max !== undefined) {
          const sliderValue = getNumberParameterWithDefault(sttParameters, key, paramConfig.default, paramConfig.min);
          return (
            <div key={key} className="col-span-2 space-y-2">
              <Label>
                {paramConfig.description || key}: {sliderValue.toFixed(2)}
              </Label>
              <Slider
                min={paramConfig.min}
                max={paramConfig.max}
                step={paramConfig.step || 1}
                value={[sliderValue]}
                onValueChange={(values: number[]) => setSttParameter(key, values[0])}
              />
              <p className="text-muted-foreground text-[0.8rem]">
                {paramConfig.min} - {paramConfig.max}
              </p>
            </div>
          );
        }
        // Number without range - use input
        return (
          <div key={key} className="col-span-2 space-y-2">
            <Label htmlFor={`stt-${key}`}>{paramConfig.description || key}</Label>
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
          // Dropdown for predefined options
          const currentValue = String(sttParameters[key] ?? paramConfig.default ?? '');
          return (
            <div key={key} className="col-span-2 space-y-2">
              <Label htmlFor={`stt-${key}`}>{paramConfig.description || key}</Label>
              <Select value={currentValue} onValueChange={(value) => setSttParameter(key, value)}>
                <SelectTrigger id={`stt-${key}`}>
                  <SelectValue />
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
          <div key={key} className="col-span-2 space-y-2">
            <Label htmlFor={`stt-${key}`}>{paramConfig.description || key}</Label>
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
      <DialogContent className="max-h-[90vh] overflow-y-auto lg:max-w-5xl">
        <DialogHeader>
          <DialogTitle>Edit Voice Agent</DialogTitle>
          <DialogDescription>Update the voice agent configuration for {selectedApp?.app_name}</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <div className="space-y-6">
              {/* Basic Information */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold">Basic Information</h3>
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
                        <FormDescription>{field.value?.length || 0}/100 characters</FormDescription>
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
                        <FormDescription>Active agents can be used to initiate calls</FormDescription>
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
                      <FormDescription>{field.value?.length || 0}/500 characters</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              {/* Configurations */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold">Configurations</h3>
                <div className="grid grid-cols-2 gap-6">
                  <FormField
                    control={form.control}
                    name="llm_config_id"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          LLM Configuration<span className="text-red-500">*</span>
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
                                {config.display_name} ({config.type})
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        {llmConfigs.length === 0 && (
                          <FormDescription className="text-amber-600">
                            No LLM configurations found. Create one first.
                          </FormDescription>
                        )}
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="tts_config_id"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          TTS Configuration<span className="text-red-500">*</span>
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
                                {config.display_name} ({config.provider})
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        {ttsConfigs.length === 0 && (
                          <FormDescription className="text-amber-600">
                            No TTS configurations found. Create one first.
                          </FormDescription>
                        )}
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="stt_config_id"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          STT Configuration<span className="text-red-500">*</span>
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
                                {config.display_name} ({config.provider})
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        {sttConfigs.length === 0 && (
                          <FormDescription className="text-amber-600">
                            No STT configurations found. Create one first.
                          </FormDescription>
                        )}
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="telephony_config_id"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          Telephony Configuration<span className="text-red-500">*</span>
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
                                {config.display_name} ({config.provider})
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        {telephonyConfigs.length === 0 && (
                          <FormDescription className="text-amber-600">
                            No telephony configurations found. Create one first.
                          </FormDescription>
                        )}
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <div className="space-y-4">
                  <h4 className="text-sm font-medium">TTS Voice Settings</h4>
                  <FormField
                    control={form.control}
                    name="tts_voice_id"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          TTS Voice ID<span className="text-red-500">*</span>
                        </FormLabel>
                        <FormControl>
                          <Input placeholder="e.g., alloy, echo, fable (OpenAI) or voice ID (ElevenLabs)" {...field} />
                        </FormControl>
                        <FormDescription>
                          Provider-specific voice identifier (e.g., for Deepgram: aura-2-helena-en)
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  {ttsProviderConfig &&
                    Object.keys(ttsProviderConfig.parameters).filter((key) => key !== 'language').length > 0 && (
                      <div className="col-span-2 space-y-4">
                        <h4 className="text-sm font-medium">TTS Parameters</h4>
                        <div className="grid grid-cols-2 gap-6">
                          {Object.keys(ttsProviderConfig.parameters)
                            .filter((key) => key !== 'language')
                            .map((key) => renderTtsParameterField(key))}
                        </div>
                      </div>
                    )}

                  {sttProviderConfig &&
                    Object.keys(sttProviderConfig.parameters).filter((key) => key !== 'language').length > 0 && (
                      <div className="col-span-2 space-y-4">
                        <h4 className="text-sm font-medium">STT Parameters</h4>
                        <div className="grid grid-cols-2 gap-6">
                          {Object.keys(sttProviderConfig.parameters)
                            .filter((key) => key !== 'language')
                            .map((key) => renderSttParameterField(key))}
                        </div>
                      </div>
                    )}
                </div>
              </div>

              {/* Phone Numbers */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold">Phone Numbers</h3>
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
                        <FormDescription>
                          Phone numbers for receiving inbound calls (E.164 format, comma-separated, globally unique)
                        </FormDescription>
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
                        <FormDescription>
                          Phone numbers for making outbound calls (E.164 format, comma-separated)
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </div>

              {/* Language Configuration */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold">Language Configuration</h3>
                <FormField
                  control={form.control}
                  name="supported_languages"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Supported Languages<span className="text-red-500">*</span>
                      </FormLabel>
                      <div className="max-h-64 overflow-y-auto rounded-md border p-4">
                        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
                          {SUPPORTED_LANGUAGES.map((lang) => (
                            <div key={lang.code} className="flex items-center space-x-2">
                              <Checkbox
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
                              <label className="text-sm leading-none font-normal peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                                {getLanguageDisplayName(lang.code)}
                              </label>
                            </div>
                          ))}
                        </div>
                      </div>
                      <FormDescription>
                        Select languages this agent can converse in. If multiple languages are selected, the agent will
                        detect the caller's language.
                      </FormDescription>
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
                      <FormDescription>
                        Language used if detection fails or for single-language agents. Must be one of the supported
                        languages.
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              {/* Behavior */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold">Behavior</h3>
                <FormField
                  control={form.control}
                  name="system_prompt"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        System Prompt<span className="text-red-500">*</span>
                      </FormLabel>
                      <FormControl>
                        <textarea
                          rows={6}
                          placeholder="You are a helpful customer support agent. Answer questions politely and professionally..."
                          className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring flex min-h-[120px] w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                          {...field}
                        />
                      </FormControl>
                      <FormDescription>Defines the agent's personality, behavior, and capabilities</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="welcome_message"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Welcome Message<span className="text-red-500">*</span>
                      </FormLabel>
                      <FormControl>
                        <textarea
                          rows={3}
                          placeholder="Hello! Thank you for calling. How can I help you today?"
                          className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring flex min-h-[80px] w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                          {...field}
                        />
                      </FormControl>
                      <FormDescription>
                        Message played at the start of the call (converted to audio via TTS)
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              {/* Advanced */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold">Advanced</h3>
                <FormField
                  control={form.control}
                  name="conversation_config"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Conversation Configuration</FormLabel>
                      <FormControl>
                        <div className="w-full">
                          <CodeMirror
                            value={field.value || '{}'}
                            onChange={field.onChange}
                            theme="dark"
                            height="200px"
                            className="w-full"
                            extensions={[langs.json()]}
                            placeholder='{\n  "max_duration_seconds": 600,\n  "silence_timeout_seconds": 10,\n  "enable_interruptions": true\n}'
                          />
                        </div>
                      </FormControl>
                      <FormDescription>
                        JSON object with conversation settings (e.g., timeouts, interruption handling)
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              {/* Tools Section */}
              <div className="space-y-4">
                <h3 className="text-sm font-semibold">Tools & Function Calling</h3>
                <VoiceAgentToolsManager appId={appId} agentId={agent.id} />
              </div>
            </div>

            <DialogFooter>
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
