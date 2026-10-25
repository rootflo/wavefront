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
import { useCreateChatbot, useGetLLMConfigs, useUpdateChatbot } from '@app/hooks';
import { Chatbot, CreateChatbotRequest, UpdateChatbotRequest } from '@app/types/chatbot';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';

import ChatbotFormFields from './ChatbotFormFields';
import { ChatbotFormValues, buildConfig, chatbotFormSchema, readTemperature } from './schemas';

interface ChatbotFormDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  namespaces: NamespaceItem[];
  /** The chatbot to edit; omit to create one. */
  chatbot?: Chatbot;
  /** Namespace preselected for a new chatbot. */
  defaultNamespace?: string;
}

const toFormValues = (chatbot: Chatbot | undefined, namespace: string): ChatbotFormValues => ({
  name: chatbot?.name ?? '',
  namespace: chatbot?.namespace ?? namespace,
  description: chatbot?.description ?? '',
  system_prompt: chatbot?.system_prompt ?? '',
  welcome_message: chatbot?.welcome_message ?? '',
  llm_config_id: chatbot?.llm_config_id ?? '',
  temperature: chatbot ? readTemperature(chatbot.config) : '',
  enabled: chatbot?.enabled ?? false,
});

const SUBMIT_LABEL = {
  create: { idle: 'Create Chatbot', busy: 'Creating...' },
  edit: { idle: 'Save Changes', busy: 'Saving...' },
};

const ChatbotFormDialog: React.FC<ChatbotFormDialogProps> = ({
  isOpen,
  onOpenChange,
  appId,
  namespaces,
  chatbot,
  defaultNamespace = 'default',
}) => {
  const createChatbot = useCreateChatbot(appId);
  const updateChatbot = useUpdateChatbot(appId);
  const { data: llmConfigs = [] } = useGetLLMConfigs(appId);
  const isEdit = !!chatbot;
  const submitting = createChatbot.isPending || updateChatbot.isPending;

  const form = useForm<ChatbotFormValues>({
    resolver: zodResolver(chatbotFormSchema),
    defaultValues: toFormValues(chatbot, defaultNamespace),
  });

  // The dialog stays mounted while it is toggled and while the selected chatbot changes, so
  // defaultValues alone would show stale data. For a new chatbot this also picks up the list's
  // current namespace filter, so the created chatbot doesn't vanish from the filtered list.
  // Safe to depend on defaultNamespace: the dialog is modal, so the filter can't change while it's open.
  useEffect(() => {
    if (isOpen) {
      form.reset(toFormValues(chatbot, defaultNamespace));
    }
  }, [chatbot, defaultNamespace, form, isOpen]);

  const close = () => onOpenChange(false);

  const onSubmit = (data: ChatbotFormValues) => {
    const config = buildConfig(data.temperature);

    if (chatbot) {
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
        config,
        enabled: data.enabled,
      };
      updateChatbot.mutate({ chatbotId: chatbot.id, data: payload }, { onSuccess: close });
      return;
    }

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
    createChatbot.mutate(payload, { onSuccess: close });
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] min-w-0 overflow-y-auto lg:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit Chatbot' : 'Create Chatbot'}</DialogTitle>
          <DialogDescription>
            {isEdit ? `Update ${chatbot.name}` : 'Configure a chatbot with a system prompt and a model'}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <ChatbotFormFields form={form} llmConfigs={llmConfigs} namespaces={namespaces} namespaceLocked={isEdit} />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={close} disabled={submitting}>
                Cancel
              </Button>
              <Button type="submit" disabled={submitting}>
                {SUBMIT_LABEL[isEdit ? 'edit' : 'create'][submitting ? 'busy' : 'idle']}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default ChatbotFormDialog;
