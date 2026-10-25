import floConsoleService from '@app/api';
import { CreateTelephonyConfigRequest, UpdateTelephonyConfigRequest } from '@app/types/telephony-config';
import { getTelephonyConfigKey, getTelephonyConfigsKey } from '../query-keys';
import { useResourceMutation } from './use-resource-mutation';

export const useCreateTelephonyConfig = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (data: CreateTelephonyConfigRequest) =>
      floConsoleService.telephonyConfigService.createTelephonyConfig(data),
    successMessage: 'Telephony configuration created successfully',
    errorMessage: 'Failed to create telephony configuration',
    invalidate: () => [appId && getTelephonyConfigsKey(appId)],
  });

export const useUpdateTelephonyConfig = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ configId, data }: { configId: string; data: UpdateTelephonyConfigRequest }) =>
      floConsoleService.telephonyConfigService.updateTelephonyConfig(configId, data),
    successMessage: 'Telephony configuration updated successfully',
    errorMessage: 'Failed to update telephony configuration',
    invalidate: ({ configId }) =>
      appId ? [getTelephonyConfigsKey(appId), getTelephonyConfigKey(appId, configId)] : [],
  });

export const useDeleteTelephonyConfig = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (configId: string) => floConsoleService.telephonyConfigService.deleteTelephonyConfig(configId),
    successMessage: 'Telephony configuration deleted successfully',
    errorMessage: 'Failed to delete telephony configuration',
    invalidate: () => [appId && getTelephonyConfigsKey(appId)],
  });
