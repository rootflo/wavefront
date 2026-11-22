import floConsoleService from '@app/api';
import { OAuthApp, CreateOAuthAppRequest, UpdateOAuthAppRequest } from '@app/types/oauth-app';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import { getOAuthAppsKey, getOAuthAppKey } from '../query-keys';

// Reads

const getOAuthAppsQueryFn = async (): Promise<OAuthApp[]> => {
  const response = await floConsoleService.oauthAppService.getAllOAuthApps();
  if (response.data?.meta?.status === 'success' && response.data.data?.apps) {
    return response.data.data.apps;
  }
  return [];
};

const getOAuthAppQueryFn = async (oauthAppId: string): Promise<OAuthApp | null> => {
  const response = await floConsoleService.oauthAppService.getOAuthApp(oauthAppId);
  return response.data?.data?.app ?? null;
};

export const useGetOAuthApps = (appId: string | undefined): UseQueryResult<OAuthApp[], Error> => {
  return useQueryInit(getOAuthAppsKey(appId || ''), getOAuthAppsQueryFn, !!appId);
};

export const useGetOAuthApp = (
  appId: string | undefined,
  oauthAppId: string | undefined
): UseQueryResult<OAuthApp | null, Error> => {
  return useQueryInit(
    getOAuthAppKey(appId || '', oauthAppId || ''),
    () => getOAuthAppQueryFn(oauthAppId!),
    !!appId && !!oauthAppId
  );
};

// Writes

export const useCreateOAuthApp = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (data: CreateOAuthAppRequest) => floConsoleService.oauthAppService.createOAuthApp(data),
    successMessage: 'OAuth app created successfully',
    errorMessage: 'Failed to create OAuth app',
    invalidate: () => [appId && getOAuthAppsKey(appId)],
  });

export const useUpdateOAuthApp = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ oauthAppId, data }: { oauthAppId: string; data: UpdateOAuthAppRequest }) =>
      floConsoleService.oauthAppService.updateOAuthApp(oauthAppId, data),
    successMessage: 'OAuth app updated successfully',
    errorMessage: 'Failed to update OAuth app',
    invalidate: ({ oauthAppId }) => (appId ? [getOAuthAppsKey(appId), getOAuthAppKey(appId, oauthAppId)] : []),
  });

export const useSetOAuthAppEnabled = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ oauthAppId, enabled }: { oauthAppId: string; name: string; enabled: boolean }) =>
      enabled
        ? floConsoleService.oauthAppService.enableOAuthApp(oauthAppId)
        : floConsoleService.oauthAppService.disableOAuthApp(oauthAppId),
    successMessage: (_, { name, enabled }) => `${name} ${enabled ? 'enabled' : 'disabled'}`,
    errorMessage: 'Failed to update OAuth app',
    invalidate: ({ oauthAppId }) => (appId ? [getOAuthAppsKey(appId), getOAuthAppKey(appId, oauthAppId)] : []),
  });

export const useDeleteOAuthApp = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (oauthAppId: string) => floConsoleService.oauthAppService.deleteOAuthApp(oauthAppId),
    successMessage: 'OAuth app deleted successfully',
    errorMessage: 'Failed to delete OAuth app',
    invalidate: () => [appId && getOAuthAppsKey(appId)],
  });
