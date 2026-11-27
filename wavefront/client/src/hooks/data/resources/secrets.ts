import floConsoleService from '@app/api';
import { CreateSecretRequest, Secret, UpdateSecretRequest } from '@app/types/secret';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import { getApiServicesKey, getSecretsKey } from '../query-keys';

// Reads

const getSecretsQueryFn = async (): Promise<Secret[]> => {
  const response = await floConsoleService.secretService.listSecrets();
  if (response.data?.meta?.status === 'success' && response.data.data?.secrets) {
    return response.data.data.secrets;
  }
  return [];
};

/** Secret names and metadata; values are never returned. */
export const useGetSecrets = (appId: string | undefined, enabled = true): UseQueryResult<Secret[], Error> => {
  return useQueryInit(getSecretsKey(appId || ''), getSecretsQueryFn, !!appId && enabled);
};

// Writes

export const useCreateSecret = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (data: CreateSecretRequest) => floConsoleService.secretService.createSecret(data),
    successMessage: 'Secret created successfully',
    errorMessage: 'Failed to create secret',
    invalidate: () => [appId && getSecretsKey(appId)],
  });

export const useUpdateSecret = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ secretId, data }: { secretId: string; data: UpdateSecretRequest }) =>
      floConsoleService.secretService.updateSecret(secretId, data),
    successMessage: (_, { data }) =>
      data.value !== undefined ? 'Secret value rotated' : 'Secret updated successfully',
    errorMessage: 'Failed to update secret',
    // A rotated value reloads the API services that use it.
    invalidate: () => (appId ? [getSecretsKey(appId), getApiServicesKey(appId)] : []),
  });

export const useDeleteSecret = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (secretId: string) => floConsoleService.secretService.deleteSecret(secretId),
    successMessage: 'Secret deleted successfully',
    // A 409 (still referenced) is shown by the page with the referencing services.
    errorMessage: false,
    invalidate: () => [appId && getSecretsKey(appId)],
  });
