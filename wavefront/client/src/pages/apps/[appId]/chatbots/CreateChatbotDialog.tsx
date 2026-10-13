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
import { Form } from '@app/components/ui/form';
import { useGetAgents, useGetLLMConfigs } from '@app/hooks';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { CreateChatbotRequest } from '@app/types/chatbot';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';

import ChatbotFormFields from './ChatbotFormFields';
import {
  CHAT_TYPE_AGENT,
  CHAT_TYPE_LLM,
  ChatbotFormValues,
  buildConfig,
  chatbotFormSchema,
  parseAgentVersion,
} from './schemas';

interface CreateChatbotDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  namespaces: NamespaceItem[];
  defaultNamespace?: string;
  onSuccess: () => void;
}

const buildDefaultValues = (namespace: string): ChatbotFormValues => ({
  chat_type: CHAT_TYPE_LLM,
  name: '',
  namespace,
  description: '',
  system_prompt: '',
  welcome_message: '',
  llm_config_id: '',
  agent_id: '',
  agent_version: '',
  temperature: '',
  enabled: false,
});

const CreateChatbotDialog: React.FC<CreateChatbotDialogProps> = ({
  isOpen,
  onOpenChange,
  appId,
  namespaces,
  defaultNamespace = 'default',
  onSuccess,
}) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const [submitting, setSubmitting] = useState(false);
  const { data: llmConfigs = [] } = useGetLLMConfigs(appId);
  const { data: agents = [] } = useGetAgents(appId);

  const form = useForm<ChatbotFormValues>({
    resolver: zodResolver(chatbotFormSchema),
    defaultValues: buildDefaultValues(defaultNamespace),
  });

  // This dialog is mounted for the life of the page and only toggled via
  // isOpen, so defaultValues is read once on first render. Without this reset,
  // changing the list's namespace filter and then opening the dialog would show
  // the namespace that was selected when the page first loaded -- and a chatbot
  // created under it would immediately vanish from the filtered list.
  //
  // Safe to depend on defaultNamespace: the dialog is modal, so the filter
  // behind it cannot be changed while the form is open and being edited.
  useEffect(() => {
    if (isOpen) {
      form.reset(buildDefaultValues(defaultNamespace));
    }
  }, [defaultNamespace, form, isOpen]);

  const onSubmit = async (data: ChatbotFormValues) => {
    setSubmitting(true);
    try {
      const payload: CreateChatbotRequest = {
        name: data.name.trim(),
        namespace: data.namespace,
        enabled: data.enabled,
      };

      // The two types take different fields, and the API rejects a mix: an
      // agent-backed chatbot gets its prompt and model from the agent.
      if (data.chat_type === CHAT_TYPE_AGENT) {
        payload.agent_id = data.agent_id;
        const agentVersion = parseAgentVersion(data.agent_version);
        if (agentVersion !== undefined) payload.agent_version = agentVersion;
      } else {
        payload.system_prompt = data.system_prompt;
        payload.llm_config_id = data.llm_config_id;
        const config = buildConfig(data.temperature);
        if (Object.keys(config).length) payload.config = config;
      }

      // Omit rather than send empty values on create, so the row stores NULL
      // and reads as "never set" instead of "deliberately blanked".
      if (data.description.trim()) payload.description = data.description.trim();
      if (data.welcome_message.trim()) payload.welcome_message = data.welcome_message;

      await floConsoleService.chatbotService.createChatbot(payload);
      notifySuccess('Chatbot created successfully');
      form.reset(buildDefaultValues(defaultNamespace));
      onSuccess();
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to create chatbot');
    } finally {
      setSubmitting(false);
    }
  };

  const handleOpenChange = (open: boolean) => {
    if (!open) form.reset(buildDefaultValues(defaultNamespace));
    onOpenChange(open);
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[90vh] min-w-0 overflow-y-auto lg:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Create Chatbot</DialogTitle>
          <DialogDescription>
            Configure a chatbot with a system prompt and a model, or back it with an agent
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <ChatbotFormFields
              form={form}
              appId={appId}
              llmConfigs={llmConfigs}
              agents={agents}
              namespaces={namespaces}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => handleOpenChange(false)} disabled={submitting}>
                Cancel
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? 'Creating...' : 'Create Chatbot'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateChatbotDialog;
