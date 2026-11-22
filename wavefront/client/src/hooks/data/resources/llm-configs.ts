import floConsoleService from '@app/api';
import { LLMInferenceConfig, CreateLLMConfigRequest, UpdateLLMConfigRequest } from '@app/types/llm-inference-config';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import { getLLMConfigsKey, getLLMConfigKey } from '../query-keys';

// Reads

const getLLMConfigsQueryFn = async (): Promise<LLMInferenceConfig[]> => {
  const response = await floConsoleService.llmInferenceService.listAllLLMConfigs();
  if (response.data?.meta?.status === 'success' && response.data.data?.configs) {
    return response.data.data.configs;
  }
  return [];
};

const getLLMConfigQueryFn = async (configId: string): Promise<LLMInferenceConfig | null> => {
  const response = await floConsoleService.llmInferenceService.getLLMConfig(configId);
  if (response.data?.data) {
    return response.data.data;
  }
  return null;
};

export const useGetLLMConfigs = (appId: string | undefined): UseQueryResult<LLMInferenceConfig[], Error> => {
  return useQueryInit(getLLMConfigsKey(appId || ''), getLLMConfigsQueryFn, !!appId);
};

export const useGetLLMConfig = (
  appId: string | undefined,
  configId: string | undefined
): UseQueryResult<LLMInferenceConfig | null, Error> => {
  return useQueryInit(
    getLLMConfigKey(appId || '', configId || ''),
    () => getLLMConfigQueryFn(configId!),
    !!appId && !!configId
  );
};

// Writes

export const useCreateLLMConfig = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (data: CreateLLMConfigRequest) => floConsoleService.llmInferenceService.createLLMConfig(data),
    successMessage: 'Model added to the Model Hub',
    errorMessage: 'Failed to add model',
    invalidate: () => [appId && getLLMConfigsKey(appId)],
  });

export const useUpdateLLMConfig = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ configId, data }: { configId: string; data: UpdateLLMConfigRequest }) =>
      floConsoleService.llmInferenceService.updateLLMConfig(configId, data),
    successMessage: 'Model updated successfully',
    errorMessage: 'Failed to update model',
    invalidate: ({ configId }) => (appId ? [getLLMConfigKey(appId, configId), getLLMConfigsKey(appId)] : []),
  });

export const useDeleteLLMConfig = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (configId: string) => floConsoleService.llmInferenceService.deleteLLMConfig(configId),
    successMessage: 'Model deleted successfully',
    errorMessage: 'Failed to delete model',
    invalidate: () => [appId && getLLMConfigsKey(appId)],
  });
