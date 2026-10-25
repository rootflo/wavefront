import floConsoleService from '@app/api';
import { CreateAppRequest, UpdateAppRequest } from '@app/types/app';
import { getAllAppsKey, getAppByIdKey } from '../query-keys';
import { useResourceMutation } from './use-resource-mutation';

/** No success toast: an auto deployment is still in progress when this resolves, so the caller reports it. */
export const useCreateApp = () =>
  useResourceMutation({
    mutationFn: (data: CreateAppRequest) => floConsoleService.appService.createApp(data),
    errorMessage: 'Failed to create app',
    invalidate: () => [getAllAppsKey()],
  });

export const useUpdateApp = () =>
  useResourceMutation({
    mutationFn: ({ appId, data }: { appId: string; data: UpdateAppRequest }) =>
      floConsoleService.appService.updateApp(appId, data),
    successMessage: 'App updated successfully',
    errorMessage: 'Failed to update app',
    invalidate: ({ appId }) => [getAppByIdKey(appId), getAllAppsKey()],
  });

export const useDeleteApp = () =>
  useResourceMutation({
    mutationFn: ({ appId, deleteDeployment }: { appId: string; appName: string; deleteDeployment: boolean }) =>
      floConsoleService.appService.deleteApp(appId, deleteDeployment),
    successMessage: (_, { appName }) => `App "${appName}" deleted successfully`,
    errorMessage: 'Failed to delete app',
    invalidate: () => [getAllAppsKey()],
  });
