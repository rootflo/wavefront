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
import { Chatbot, UpdateChatbotRequest } from '@app/types/chatbot';
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
  readTemperature,
} from './schemas';

interface EditChatbotDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  chatbot: Chatbot;
  namespaces: NamespaceItem[];
  onSuccess: () => void;
}

const toFormValues = (chatbot: Chatbot): ChatbotFormValues => ({
  chat_type: chatbot.agent_id ? CHAT_TYPE_AGENT : CHAT_TYPE_LLM,
  name: chatbot.name,
  namespace: chatbot.namespace,
  description: chatbot.description ?? '',
  system_prompt: chatbot.system_prompt ?? '',
  welcome_message: chatbot.welcome_message ?? '',
  llm_config_id: chatbot.llm_config_id ?? '',
  agent_id: chatbot.agent_id ?? '',
  agent_version: chatbot.agent_version ? String(chatbot.agent_version) : '',
  temperature: readTemperature(chatbot.config),
  enabled: chatbot.enabled,
});

const EditChatbotDialog: React.FC<EditChatbotDialogProps> = ({
  isOpen,
  onOpenChange,
  appId,
  chatbot,
  namespaces,
  onSuccess,
}) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const [submitting, setSubmitting] = useState(false);
  const { data: llmConfigs = [] } = useGetLLMConfigs(appId);
  const { data: agents = [] } = useGetAgents(appId);

  const form = useForm<ChatbotFormValues>({
    resolver: zodResolver(chatbotFormSchema),
    defaultValues: toFormValues(chatbot),
  });

  // The dialog stays mounted while the selected row changes, so defaultValues
  // alone would keep showing the previously opened chatbot.
  useEffect(() => {
    form.reset(toFormValues(chatbot));
  }, [chatbot, form]);

  const onSubmit = async (data: ChatbotFormValues) => {
    // A pinned chatbot stays pinned (the API cannot clear it), and changing the
    // agent blanks the version. Sending no version then would keep the old
    // number against the new agent, so one has to be chosen.
    if (data.chat_type === CHAT_TYPE_AGENT && chatbot.agent_version && !data.agent_version.trim()) {
      form.setError('agent_version', { message: 'Select a version' });
      return;
    }

    setSubmitting(true);
    try {
      // Every editable field is sent with a concrete value on purpose. The API
      // reads null/absent as "not supplied", so clearing a field requires an
      // empty value ('' for text, {} for config) -- omitting it would silently
      // leave the old value in place. `namespace` is not sent at all: the
      // update API does not accept it.
      const payload: UpdateChatbotRequest = {
        name: data.name.trim(),
        description: data.description.trim(),
        welcome_message: data.welcome_message,
        enabled: data.enabled,
      };

      // A chatbot keeps its type, and the API rejects the other type's fields.
      if (data.chat_type === CHAT_TYPE_AGENT) {
        payload.agent_id = data.agent_id;
        // Blank is left out, which the API reads as "not supplied": a pinned
        // version can be moved here but not cleared, so the form does not
        // offer "follow current" for a chatbot that is pinned.
        const agentVersion = parseAgentVersion(data.agent_version);
        if (agentVersion !== undefined) payload.agent_version = agentVersion;
      } else {
        payload.system_prompt = data.system_prompt;
        payload.llm_config_id = data.llm_config_id;
        payload.config = buildConfig(data.temperature);
      }

      await floConsoleService.chatbotService.updateChatbot(chatbot.id, payload);
      notifySuccess('Chatbot updated successfully');
      onSuccess();
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to update chatbot');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] min-w-0 overflow-y-auto lg:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Edit Chatbot</DialogTitle>
          <DialogDescription>Update {chatbot.name}</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <ChatbotFormFields
              form={form}
              appId={appId}
              llmConfigs={llmConfigs}
              agents={agents}
              namespaces={namespaces}
              namespaceLocked
              chatTypeLocked
              pinnedAgentVersion={chatbot.agent_version}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
                Cancel
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? 'Saving...' : 'Save Changes'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default EditChatbotDialog;
