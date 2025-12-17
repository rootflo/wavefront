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
import {
  useGetLLMConfigs,
  useGetSttConfigs,
  useGetTelephonyConfigs,
  useGetTtsConfigs,
} from '@app/hooks/data/fetch-hooks';
import { extractErrorMessage } from '@app/lib/utils';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { UpdateVoiceAgentRequest, VoiceAgent } from '@app/types/voice-agent';
import { zodResolver } from '@hookform/resolvers/zod';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const updateVoiceAgentSchema = z.object({
  name: z.string().min(1, 'Name is required').max(100, 'Name must be 100 characters or less'),
  description: z.string().max(500, 'Description must be 500 characters or less').optional(),
  llm_config_id: z.string().min(1, 'LLM configuration is required'),
  tts_config_id: z.string().min(1, 'TTS configuration is required'),
  stt_config_id: z.string().min(1, 'STT configuration is required'),
  telephony_config_id: z.string().min(1, 'Telephony configuration is required'),
  system_prompt: z.string().min(1, 'System prompt is required'),
  welcome_message: z.string().min(1, 'Welcome message is required'),
  conversation_config: z.string().optional(),
  status: z.enum(['active', 'inactive']),
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

  const form = useForm<UpdateVoiceAgentInput>({
    resolver: zodResolver(updateVoiceAgentSchema),
    defaultValues: {
      name: agent.name,
      description: agent.description || '',
      llm_config_id: agent.llm_config_id,
      tts_config_id: agent.tts_config_id,
      stt_config_id: agent.stt_config_id,
      telephony_config_id: agent.telephony_config_id,
      system_prompt: agent.system_prompt,
      welcome_message: agent.welcome_message,
      conversation_config: agent.conversation_config ? JSON.stringify(agent.conversation_config, null, 2) : '{}',
      status: agent.status,
    },
  });

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
        system_prompt: agent.system_prompt,
        welcome_message: agent.welcome_message,
        conversation_config: agent.conversation_config ? JSON.stringify(agent.conversation_config, null, 2) : '{}',
        status: agent.status,
      });
    }
  }, [isOpen, agent, form]);

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

    setUpdating(true);
    try {
      const requestData: UpdateVoiceAgentRequest = {
        name: data.name.trim(),
        description: data.description?.trim() || null,
        llm_config_id: data.llm_config_id.trim(),
        tts_config_id: data.tts_config_id.trim(),
        stt_config_id: data.stt_config_id.trim(),
        telephony_config_id: data.telephony_config_id.trim(),
        system_prompt: data.system_prompt.trim(),
        welcome_message: data.welcome_message.trim(),
        conversation_config: conversationConfig,
        status: data.status,
      };

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
