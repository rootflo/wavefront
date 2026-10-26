import floConsoleService from '@app/api';
import {
  MessageProcessor,
  MessageProcessorListItem,
  CreateMessageProcessorRequest,
  UpdateMessageProcessorRequest,
} from '@app/types/message-processor';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import { getMessageProcessorsKey, getMessageProcessorKey } from '../query-keys';

// Reads

const getMessageProcessorsQueryFn = async (): Promise<MessageProcessorListItem[]> => {
  const response = await floConsoleService.messageProcessorService.listMessageProcessors();
  if (response.data?.data?.processors && Array.isArray(response.data.data.processors)) {
    return response.data.data.processors;
  }
  return [];
};

const getMessageProcessorQueryFn = async (processorId: string): Promise<MessageProcessor | null> => {
  const response = await floConsoleService.messageProcessorService.getMessageProcessor(processorId);
  if (response.data?.data?.processor) {
    return response.data.data.processor;
  }
  return null;
};

export const useGetMessageProcessors = (
  appId: string | undefined
): UseQueryResult<MessageProcessorListItem[], Error> => {
  return useQueryInit(getMessageProcessorsKey(appId || ''), getMessageProcessorsQueryFn, !!appId);
};

export const useGetMessageProcessor = (
  appId: string | undefined,
  processorId: string | undefined
): UseQueryResult<MessageProcessor | null, Error> => {
  return useQueryInit(
    getMessageProcessorKey(appId || '', processorId || ''),
    () => getMessageProcessorQueryFn(processorId!),
    !!appId && !!processorId
  );
};

// Writes

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
