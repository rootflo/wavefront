import floConsoleService from '@app/api';
import { CreateTriggerRequest } from '@app/types/trigger';
import { getTriggersKey } from '../query-keys';
import { useResourceMutation } from './use-resource-mutation';

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
