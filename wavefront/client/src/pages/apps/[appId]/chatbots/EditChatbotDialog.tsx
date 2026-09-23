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
import { useGetLLMConfigs } from '@app/hooks';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { Chatbot, UpdateChatbotRequest } from '@app/types/chatbot';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';

import ChatbotFormFields from './ChatbotFormFields';
import { ChatbotFormValues, buildConfig, chatbotFormSchema, readTemperature } from './schemas';

interface EditChatbotDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  chatbot: Chatbot;
  namespaces: NamespaceItem[];
  onSuccess: () => void;
}

const toFormValues = (chatbot: Chatbot): ChatbotFormValues => ({
  name: chatbot.name,
  namespace: chatbot.namespace,
  description: chatbot.description ?? '',
  system_prompt: chatbot.system_prompt,
  welcome_message: chatbot.welcome_message ?? '',
  llm_config_id: chatbot.llm_config_id,
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
        system_prompt: data.system_prompt,
        welcome_message: data.welcome_message,
        llm_config_id: data.llm_config_id,
        config: buildConfig(data.temperature),
        enabled: data.enabled,
      };

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
            <ChatbotFormFields form={form} llmConfigs={llmConfigs} namespaces={namespaces} namespaceLocked />

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
