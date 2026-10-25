import floConsoleService from '@app/api';
import { CreateConfigurationRequest, UpsertConfigurationRequest } from '@app/types/configuration';
import { getConfigurationKey, getConfigurationsKey } from '../query-keys';
import { useResourceMutation } from './use-resource-mutation';

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
