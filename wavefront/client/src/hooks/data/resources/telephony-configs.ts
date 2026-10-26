import floConsoleService from '@app/api';
import {
  TelephonyConfig,
  CreateTelephonyConfigRequest,
  UpdateTelephonyConfigRequest,
} from '@app/types/telephony-config';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import { getTelephonyConfigsKey, getTelephonyConfigKey } from '../query-keys';

// Reads

const getTelephonyConfigsQueryFn = async (): Promise<TelephonyConfig[]> => {
  const response = await floConsoleService.telephonyConfigService.listAllTelephonyConfigs();
  if (response.data?.meta?.status === 'success' && response.data.data?.telephony_configs) {
    return response.data.data.telephony_configs;
  }
  return [];
};

const getTelephonyConfigQueryFn = async (configId: string): Promise<TelephonyConfig | null> => {
  const response = await floConsoleService.telephonyConfigService.getTelephonyConfig(configId);
  if (response.data?.data) {
    return response.data.data;
  }
  return null;
};

export const useGetTelephonyConfigs = (appId: string | undefined): UseQueryResult<TelephonyConfig[], Error> => {
  return useQueryInit(getTelephonyConfigsKey(appId || ''), getTelephonyConfigsQueryFn, !!appId);
};

export const useGetTelephonyConfig = (
  appId: string | undefined,
  configId: string | undefined
): UseQueryResult<TelephonyConfig | null, Error> => {
  return useQueryInit(
    getTelephonyConfigKey(appId || '', configId || ''),
    () => getTelephonyConfigQueryFn(configId!),
    !!appId && !!configId
  );
};

// Writes

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
