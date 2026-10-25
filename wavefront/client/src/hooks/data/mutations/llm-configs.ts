import floConsoleService from '@app/api';
import { CreateLLMConfigRequest, UpdateLLMConfigRequest } from '@app/types/llm-inference-config';
import { getLLMConfigKey, getLLMConfigsKey } from '../query-keys';
import { useResourceMutation } from './use-resource-mutation';

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
