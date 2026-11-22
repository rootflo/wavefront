import floConsoleService from '@app/api';
import { ApiServiceItem } from '@app/types/api-service';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import { getApiServicesKey, getApiServiceKey } from '../query-keys';

// Reads

const getApiServicesQueryFn = async (): Promise<ApiServiceItem[]> => {
  const response = await floConsoleService.apiServiceService.listApiServices();
  if (response.data?.meta?.status === 'success' && response.data.data?.services) {
    return response.data.data.services;
  }
  return [];
};

const getApiServiceQueryFn = async (serviceId: string): Promise<ApiServiceItem | null> => {
  const response = await floConsoleService.apiServiceService.getApiService(serviceId);
  if (response.data?.data) {
    return response.data.data;
  }
  return null;
};

export const useGetApiServices = (appId: string | undefined): UseQueryResult<ApiServiceItem[], Error> => {
  return useQueryInit(getApiServicesKey(appId || ''), getApiServicesQueryFn, !!appId);
};

export const useGetApiService = (
  appId: string | undefined,
  serviceId: string | undefined
): UseQueryResult<ApiServiceItem | null, Error> => {
  return useQueryInit(
    getApiServiceKey(appId || '', serviceId || ''),
    () => getApiServiceQueryFn(serviceId!),
    !!appId && !!serviceId
  );
};

// Writes

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
