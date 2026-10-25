import floConsoleService from '@app/api';
import { CreateChatbotRequest, UpdateChatbotRequest } from '@app/types/chatbot';
import { getChatbotsKey } from '../query-keys';
import { useResourceMutation } from './use-resource-mutation';

export const useCreateChatbot = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (data: CreateChatbotRequest) => floConsoleService.chatbotService.createChatbot(data),
    successMessage: 'Chatbot created successfully',
    errorMessage: 'Failed to create chatbot',
    invalidate: () => [appId && getChatbotsKey(appId)],
  });

export const useUpdateChatbot = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ chatbotId, data }: { chatbotId: string; data: UpdateChatbotRequest }) =>
      floConsoleService.chatbotService.updateChatbot(chatbotId, data),
    successMessage: 'Chatbot updated successfully',
    errorMessage: 'Failed to update chatbot',
    invalidate: () => [appId && getChatbotsKey(appId)],
  });

export const useSetChatbotEnabled = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ chatbotId, enabled }: { chatbotId: string; enabled: boolean }) =>
      floConsoleService.chatbotService.updateChatbot(chatbotId, { enabled }),
    successMessage: (_, { enabled }) => (enabled ? 'Chatbot enabled' : 'Chatbot disabled'),
    errorMessage: 'Failed to update chatbot',
    invalidate: () => [appId && getChatbotsKey(appId)],
  });

export const useDeleteChatbot = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (chatbotId: string) => floConsoleService.chatbotService.deleteChatbot(chatbotId),
    successMessage: 'Chatbot deleted successfully',
    errorMessage: 'Failed to delete chatbot',
    invalidate: () => [appId && getChatbotsKey(appId)],
  });
