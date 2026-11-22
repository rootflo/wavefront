import floConsoleService from '@app/api';
import { useQueryInit } from '@app/lib/react-query';
import { App, CreateAppRequest, UpdateAppRequest } from '@app/types/app';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import { getAllAppsKey, getAppByIdKey } from '../query-keys';

// Reads

const getAllAppsQueryFn = async () => {
  const {
    data: { data = { apps: [] } },
  } = await floConsoleService.appService.getAllApps();
  return data.apps;
};

const getAppByIdFn = async (appId: string) => {
  const {
    data: { data },
  } = await floConsoleService.appService.getAppById(appId);
  return data?.app;
};

// Voice Agent Tools Query Functions

export const useGetAllApps = (enabled: boolean): UseQueryResult<App[], Error> => {
  return useQueryInit(getAllAppsKey(), getAllAppsQueryFn, enabled);
};

export const useGetAppById = (appId: string, enabled: boolean = true): UseQueryResult<App | undefined, Error> => {
  return useQueryInit<App | undefined>(getAppByIdKey(appId), () => getAppByIdFn(appId), enabled);
};

// Writes

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
