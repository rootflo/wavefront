import floConsoleService from '@app/api';
import { SttConfig, CreateSttConfigRequest, SttProvider, UpdateSttConfigRequest } from '@app/types/stt-config';
import { TtsConfig, CreateTtsConfigRequest, TtsProvider, UpdateTtsConfigRequest } from '@app/types/tts-config';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import { getTtsConfigsKey, getSttConfigsKey, getTtsConfigKey, getSttConfigKey } from '../query-keys';

// Reads

const getTtsConfigsQueryFn = async (): Promise<TtsConfig[]> => {
  const response = await floConsoleService.ttsConfigService.listAllTtsConfigs();
  if (response.data?.meta?.status === 'success' && response.data.data?.tts_configs) {
    return response.data.data.tts_configs;
  }
  return [];
};

const getSttConfigsQueryFn = async (): Promise<SttConfig[]> => {
  const response = await floConsoleService.sttConfigService.listAllSttConfigs();
  if (response.data?.meta?.status === 'success' && response.data.data?.stt_configs) {
    return response.data.data.stt_configs;
  }
  return [];
};

const getTtsConfigQueryFn = async (configId: string): Promise<TtsConfig | null> => {
  const response = await floConsoleService.ttsConfigService.getTtsConfig(configId);
  if (response.data?.data) {
    return response.data.data;
  }
  return null;
};

const getSttConfigQueryFn = async (configId: string): Promise<SttConfig | null> => {
  const response = await floConsoleService.sttConfigService.getSttConfig(configId);
  if (response.data?.data) {
    return response.data.data;
  }
  return null;
};

export const useGetTtsConfigs = (appId: string | undefined): UseQueryResult<TtsConfig[], Error> => {
  return useQueryInit(getTtsConfigsKey(appId || ''), getTtsConfigsQueryFn, !!appId);
};

export const useGetSttConfigs = (appId: string | undefined): UseQueryResult<SttConfig[], Error> => {
  return useQueryInit(getSttConfigsKey(appId || ''), getSttConfigsQueryFn, !!appId);
};

export const useGetTtsConfig = (
  appId: string | undefined,
  configId: string | undefined
): UseQueryResult<TtsConfig | null, Error> => {
  return useQueryInit(
    getTtsConfigKey(appId || '', configId || ''),
    () => getTtsConfigQueryFn(configId!),
    !!appId && !!configId
  );
};

export const useGetSttConfig = (
  appId: string | undefined,
  configId: string | undefined
): UseQueryResult<SttConfig | null, Error> => {
  return useQueryInit(
    getSttConfigKey(appId || '', configId || ''),
    () => getSttConfigQueryFn(configId!),
    !!appId && !!configId
  );
};

// Writes

/** Speech-to-text and text-to-speech provider configs share one shape and one set of screens. */
export type VoiceProviderKind = 'stt' | 'tts';

export type CreateVoiceProviderConfigRequest = Omit<CreateSttConfigRequest, 'provider'> & {
  provider: SttProvider | TtsProvider;
};
export type UpdateVoiceProviderConfigRequest = UpdateSttConfigRequest & UpdateTtsConfigRequest;

const api = {
  stt: {
    label: 'STT',
    create: (data: CreateVoiceProviderConfigRequest) =>
      floConsoleService.sttConfigService.createSttConfig(data as CreateSttConfigRequest),
    update: (id: string, data: UpdateVoiceProviderConfigRequest) =>
      floConsoleService.sttConfigService.updateSttConfig(id, data),
    remove: (id: string) => floConsoleService.sttConfigService.deleteSttConfig(id),
    listKey: getSttConfigsKey,
    itemKey: getSttConfigKey,
  },
  tts: {
    label: 'TTS',
    create: (data: CreateVoiceProviderConfigRequest) =>
      floConsoleService.ttsConfigService.createTtsConfig(data as CreateTtsConfigRequest),
    update: (id: string, data: UpdateVoiceProviderConfigRequest) =>
      floConsoleService.ttsConfigService.updateTtsConfig(id, data),
    remove: (id: string) => floConsoleService.ttsConfigService.deleteTtsConfig(id),
    listKey: getTtsConfigsKey,
    itemKey: getTtsConfigKey,
  },
};

export const useCreateVoiceProviderConfig = (kind: VoiceProviderKind, appId: string | undefined) =>
  useResourceMutation({
    mutationFn: async (data: CreateVoiceProviderConfigRequest) => {
      await api[kind].create(data);
    },
    successMessage: `${api[kind].label} configuration created successfully`,
    errorMessage: `Failed to create ${api[kind].label} configuration`,
    invalidate: () => [appId && api[kind].listKey(appId)],
  });

export const useUpdateVoiceProviderConfig = (kind: VoiceProviderKind, appId: string | undefined) =>
  useResourceMutation({
    mutationFn: async ({ configId, data }: { configId: string; data: UpdateVoiceProviderConfigRequest }) => {
      await api[kind].update(configId, data);
    },
    successMessage: `${api[kind].label} configuration updated successfully`,
    errorMessage: `Failed to update ${api[kind].label} configuration`,
    invalidate: ({ configId }) => (appId ? [api[kind].listKey(appId), api[kind].itemKey(appId, configId)] : []),
  });

export const useDeleteVoiceProviderConfig = (kind: VoiceProviderKind, appId: string | undefined) =>
  useResourceMutation({
    mutationFn: async (configId: string) => {
      await api[kind].remove(configId);
    },
    successMessage: `${api[kind].label} configuration deleted successfully`,
    errorMessage: `Failed to delete ${api[kind].label} configuration`,
    invalidate: () => [appId && api[kind].listKey(appId)],
  });
