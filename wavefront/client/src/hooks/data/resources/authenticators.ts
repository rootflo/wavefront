import floConsoleService from '@app/api';
import { Authenticator, CreateAuthenticatorRequest, UpdateAuthenticatorRequest } from '@app/types/authenticator';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import { getAuthenticatorsKey, getAuthenticatorKey } from '../query-keys';

// Reads

const getAuthenticatorsQueryFn = async (): Promise<Authenticator[]> => {
  const response = await floConsoleService.authenticatorService.getAllAuthenticators();
  if (response.data?.meta?.status === 'success' && response.data.data?.authenticators) {
    return response.data.data.authenticators;
  }
  return [];
};

const getAuthenticatorQueryFn = async (authId: string): Promise<Authenticator | null> => {
  const response = await floConsoleService.authenticatorService.getAuthenticator(authId);
  if (response.data?.data) {
    return response.data.data;
  }
  return null;
};

export const useGetAuthenticators = (appId: string | undefined): UseQueryResult<Authenticator[], Error> => {
  return useQueryInit(getAuthenticatorsKey(appId || ''), getAuthenticatorsQueryFn, !!appId);
};

export const useGetAuthenticator = (
  appId: string | undefined,
  authId: string | undefined
): UseQueryResult<Authenticator | null, Error> => {
  return useQueryInit(
    getAuthenticatorKey(appId || '', authId || ''),
    () => getAuthenticatorQueryFn(authId!),
    !!appId && !!authId
  );
};

// Writes

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
