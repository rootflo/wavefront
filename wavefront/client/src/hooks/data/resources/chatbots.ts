import floConsoleService from '@app/api';
import { Chatbot, CreateChatbotRequest, UpdateChatbotRequest } from '@app/types/chatbot';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import { getChatbotsKey } from '../query-keys';

// Reads

const getChatbotsQueryFn = async (namespace?: string): Promise<Chatbot[]> => {
  const response = await floConsoleService.chatbotService.listAllChatbots(namespace);
  if (response.data?.meta?.status === 'success' && response.data.data?.chatbots) {
    return response.data.data.chatbots;
  }
  return [];
};

export const useGetChatbots = (appId: string | undefined, namespace?: string): UseQueryResult<Chatbot[], Error> => {
  return useQueryInit(getChatbotsKey(appId || '', namespace), () => getChatbotsQueryFn(namespace), !!appId);
};

// Writes

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
