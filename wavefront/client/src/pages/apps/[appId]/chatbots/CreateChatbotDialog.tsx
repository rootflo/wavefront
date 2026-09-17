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
import { CreateChatbotRequest } from '@app/types/chatbot';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useState } from 'react';
import { useForm } from 'react-hook-form';

import ChatbotFormFields from './ChatbotFormFields';
import { ChatbotFormValues, buildConfig, chatbotFormSchema } from './schemas';

interface CreateChatbotDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  namespaces: NamespaceItem[];
  defaultNamespace?: string;
  onSuccess: () => void;
}

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

  const form = useForm<ChatbotFormValues>({
    resolver: zodResolver(chatbotFormSchema),
    defaultValues: {
      name: '',
      namespace: defaultNamespace,
      description: '',
      system_prompt: '',
      welcome_message: '',
      llm_config_id: '',
      temperature: '',
      enabled: false,
    },
  });

  const onSubmit = async (data: ChatbotFormValues) => {
    setSubmitting(true);
    try {
      const config = buildConfig(data.temperature);
      const payload: CreateChatbotRequest = {
        name: data.name.trim(),
        namespace: data.namespace,
        system_prompt: data.system_prompt,
        llm_config_id: data.llm_config_id,
        enabled: data.enabled,
      };

      // Omit rather than send empty values on create, so the row stores NULL
      // and reads as "never set" instead of "deliberately blanked".
      if (data.description.trim()) payload.description = data.description.trim();
      if (data.welcome_message.trim()) payload.welcome_message = data.welcome_message;
      if (Object.keys(config).length) payload.config = config;

      await floConsoleService.chatbotService.createChatbot(payload);
      notifySuccess('Chatbot created successfully');
      form.reset();
      onSuccess();
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to create chatbot');
    } finally {
      setSubmitting(false);
    }
  };

  const handleOpenChange = (open: boolean) => {
    if (!open) form.reset();
    onOpenChange(open);
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[90vh] min-w-0 overflow-y-auto lg:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Create Chatbot</DialogTitle>
          <DialogDescription>Configure a chatbot with a system prompt and a model</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <ChatbotFormFields form={form} llmConfigs={llmConfigs} namespaces={namespaces} />

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
