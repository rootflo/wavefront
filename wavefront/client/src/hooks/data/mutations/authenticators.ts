import floConsoleService from '@app/api';
import { CreateAuthenticatorRequest, UpdateAuthenticatorRequest } from '@app/types/authenticator';
import { getAuthenticatorKey, getAuthenticatorsKey } from '../query-keys';
import { useResourceMutation } from './use-resource-mutation';

export const useCreateAuthenticator = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (data: CreateAuthenticatorRequest) => floConsoleService.authenticatorService.createAuthenticator(data),
    successMessage: 'Authenticator created successfully',
    errorMessage: 'Failed to create authenticator',
    invalidate: () => [appId && getAuthenticatorsKey(appId)],
  });

export const useUpdateAuthenticator = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ authId, data }: { authId: string; data: UpdateAuthenticatorRequest }) =>
      floConsoleService.authenticatorService.updateAuthenticator(authId, data),
    successMessage: 'Authenticator updated successfully',
    errorMessage: 'Failed to update authenticator',
    invalidate: ({ authId }) => (appId ? [getAuthenticatorKey(appId, authId), getAuthenticatorsKey(appId)] : []),
  });

export const useSetAuthenticatorEnabled = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ authId, enabled }: { authId: string; enabled: boolean }) =>
      enabled
        ? floConsoleService.authenticatorService.enableAuthenticator(authId)
        : floConsoleService.authenticatorService.disableAuthenticator(authId),
    successMessage: (_, { enabled }) => `Authenticator ${enabled ? 'enabled' : 'disabled'} successfully`,
    errorMessage: 'Failed to toggle authenticator',
    invalidate: ({ authId }) => (appId ? [getAuthenticatorKey(appId, authId), getAuthenticatorsKey(appId)] : []),
  });

export const useDeleteAuthenticator = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (authId: string) => floConsoleService.authenticatorService.deleteAuthenticator(authId),
    successMessage: 'Authenticator deleted successfully',
    errorMessage: 'Failed to delete authenticator',
    invalidate: () => [appId && getAuthenticatorsKey(appId)],
  });
