import floConsoleService from '@app/api';
import {
  ConfigurationListItem,
  ConfigurationValue,
  CreateConfigurationRequest,
  UpsertConfigurationRequest,
} from '@app/types/configuration';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import { getConfigurationsKey, getConfigurationKey } from '../query-keys';

// Reads

const getConfigurationsQueryFn = async (namespace?: string): Promise<ConfigurationListItem[]> => {
  const response = await floConsoleService.configurationService.listConfigurations(namespace);
  if (response.data?.data?.configurations && Array.isArray(response.data.data.configurations)) {
    return response.data.data.configurations;
  }
  return [];
};

/**
 * Returns the configuration document. `null` means "not found"; an empty object
 * is a legitimate stored value, so the two must not be conflated.
 */

const getConfigurationQueryFn = async (namespace: string, key: string): Promise<ConfigurationValue | null> => {
  const response = await floConsoleService.configurationService.getConfiguration(namespace, key);
  return response.data?.data ?? null;
};

export const useGetConfigurations = (
  appId: string | undefined,
  namespace?: string
): UseQueryResult<ConfigurationListItem[], Error> => {
  return useQueryInit(getConfigurationsKey(appId || '', namespace), () => getConfigurationsQueryFn(namespace), !!appId);
};

export const useGetConfiguration = (
  appId: string | undefined,
  namespace: string | undefined,
  key: string | undefined
): UseQueryResult<ConfigurationValue | null, Error> => {
  return useQueryInit(
    getConfigurationKey(appId || '', namespace || '', key || ''),
    () => getConfigurationQueryFn(namespace!, key!),
    !!appId && !!namespace && !!key
  );
};

// Writes

type ConfigurationRef = { namespace: string; key: string };

export const useCreateConfiguration = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (data: CreateConfigurationRequest) => floConsoleService.configurationService.createConfiguration(data),
    successMessage: 'Configuration created successfully',
    errorMessage: 'Failed to create configuration',
    invalidate: () => [appId && getConfigurationsKey(appId)],
  });

export const useSaveConfiguration = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ namespace, key, data }: ConfigurationRef & { data: UpsertConfigurationRequest }) =>
      floConsoleService.configurationService.upsertConfiguration(namespace, key, data),
    successMessage: 'Configuration saved successfully',
    errorMessage: 'Failed to save configuration',
    invalidate: ({ namespace, key }) =>
      appId ? [getConfigurationKey(appId, namespace, key), getConfigurationsKey(appId)] : [],
  });

export const useDeleteConfiguration = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ namespace, key }: ConfigurationRef) =>
      floConsoleService.configurationService.deleteConfiguration(namespace, key),
    successMessage: 'Configuration deleted successfully',
    errorMessage: 'Failed to delete configuration',
    invalidate: () => [appId && getConfigurationsKey(appId)],
  });
