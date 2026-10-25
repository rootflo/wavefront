import floConsoleService from '@app/api';
import { getApiServiceKey, getApiServicesKey } from '../query-keys';
import { useResourceMutation } from './use-resource-mutation';

export const useCreateApiService = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (yamlContent: string) => floConsoleService.apiServiceService.createApiService(yamlContent),
    successMessage: 'API Service created successfully',
    errorMessage: 'Failed to create API service',
    invalidate: () => [appId && getApiServicesKey(appId)],
  });

export const useUpdateApiService = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ serviceId, yamlContent }: { serviceId: string; yamlContent: string }) =>
      floConsoleService.apiServiceService.updateApiService(serviceId, yamlContent),
    successMessage: 'API Service updated successfully',
    errorMessage: 'Failed to update API service',
    invalidate: ({ serviceId }) => (appId ? [getApiServiceKey(appId, serviceId), getApiServicesKey(appId)] : []),
  });

export const useDeleteApiService = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (serviceId: string) => floConsoleService.apiServiceService.deleteApiService(serviceId),
    successMessage: 'API Service deleted successfully',
    errorMessage: 'Failed to delete API service',
    invalidate: () => [appId && getApiServicesKey(appId)],
  });
