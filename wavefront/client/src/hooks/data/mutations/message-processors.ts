import floConsoleService from '@app/api';
import { CreateMessageProcessorRequest, UpdateMessageProcessorRequest } from '@app/types/message-processor';
import { getMessageProcessorKey, getMessageProcessorsKey } from '../query-keys';
import { useResourceMutation } from './use-resource-mutation';

// Message processors are shown as "functions" in the UI

export const useCreateMessageProcessor = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (data: CreateMessageProcessorRequest) =>
      floConsoleService.messageProcessorService.createMessageProcessor(data),
    successMessage: 'Function created successfully',
    errorMessage: 'Failed to create function',
    invalidate: () => [appId && getMessageProcessorsKey(appId)],
  });

export const useUpdateMessageProcessor = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ processorId, data }: { processorId: string; data: UpdateMessageProcessorRequest }) =>
      floConsoleService.messageProcessorService.updateMessageProcessor(processorId, data),
    successMessage: 'Function updated successfully',
    errorMessage: 'Failed to update function',
    invalidate: ({ processorId }) =>
      appId ? [getMessageProcessorKey(appId, processorId), getMessageProcessorsKey(appId)] : [],
  });

export const useDeleteMessageProcessor = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (processorId: string) => floConsoleService.messageProcessorService.deleteMessageProcessor(processorId),
    successMessage: 'Function deleted successfully',
    errorMessage: 'Failed to delete function',
    invalidate: () => [appId && getMessageProcessorsKey(appId)],
  });
