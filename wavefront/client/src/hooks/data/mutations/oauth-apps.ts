import floConsoleService from '@app/api';
import { CreateOAuthAppRequest, UpdateOAuthAppRequest } from '@app/types/oauth-app';
import { getOAuthAppKey, getOAuthAppsKey } from '../query-keys';
import { useResourceMutation } from './use-resource-mutation';

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
