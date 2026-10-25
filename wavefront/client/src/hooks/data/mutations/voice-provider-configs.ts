import floConsoleService from '@app/api';
import { CreateSttConfigRequest, SttProvider, UpdateSttConfigRequest } from '@app/types/stt-config';
import { CreateTtsConfigRequest, TtsProvider, UpdateTtsConfigRequest } from '@app/types/tts-config';
import { getSttConfigKey, getSttConfigsKey, getTtsConfigKey, getTtsConfigsKey } from '../query-keys';
import { useResourceMutation } from './use-resource-mutation';

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
