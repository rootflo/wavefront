import floConsoleService from '@app/api';
import { Trigger, CreateTriggerRequest } from '@app/types/trigger';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import { getTriggersKey } from '../query-keys';

// Reads

const getTriggersQueryFn = async (): Promise<Trigger[]> => {
  const response = await floConsoleService.triggerService.listTriggers({ limit: 500 });
  if (response.data?.meta?.status === 'success' && Array.isArray(response.data.data?.data)) {
    return response.data.data.data.filter((trigger) => trigger.status !== 'deleted');
  }
  return [];
};

export const useGetTriggers = (appId: string | undefined): UseQueryResult<Trigger[], Error> => {
  return useQueryInit(getTriggersKey(appId || ''), getTriggersQueryFn, !!appId);
};

// Voice Agent Tools Hooks

// Writes

/** No error toast: the trigger form shows a failure inline. */
export const useCreateTrigger = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (request: CreateTriggerRequest) => floConsoleService.triggerService.createTrigger(request),
    successMessage: 'Trigger created successfully',
    errorMessage: false,
    invalidate: () => [appId && getTriggersKey(appId)],
  });

export const useSetTriggerPaused = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ triggerId, paused }: { triggerId: string; paused: boolean }) =>
      paused
        ? floConsoleService.triggerService.pauseTrigger(triggerId)
        : floConsoleService.triggerService.resumeTrigger(triggerId),
    successMessage: (_, { paused }) => (paused ? 'Trigger paused' : 'Trigger resumed'),
    errorMessage: 'Failed to update trigger status',
    invalidate: () => [appId && getTriggersKey(appId)],
  });

export const useRetryTrigger = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (triggerId: string) => floConsoleService.triggerService.retryTrigger(triggerId),
    successMessage: 'Watch registration retried',
    errorMessage: 'Failed to retry trigger',
    invalidate: () => [appId && getTriggersKey(appId)],
  });

export const useDeleteTrigger = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (triggerId: string) => floConsoleService.triggerService.deleteTrigger(triggerId),
    successMessage: 'Trigger deleted',
    errorMessage: 'Failed to delete trigger',
    invalidate: () => [appId && getTriggersKey(appId)],
  });
