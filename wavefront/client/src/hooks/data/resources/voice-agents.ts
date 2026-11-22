import floConsoleService from '@app/api';
import {
  VoiceAgent,
  VoiceAgentListItem,
  CreateVoiceAgentRequest,
  UpdateVoiceAgentRequest,
} from '@app/types/voice-agent';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import { getVoiceAgentsKey, getVoiceAgentKey, getVoiceAgentToolsKey } from '../query-keys';

// Reads

const getVoiceAgentsQueryFn = async (): Promise<VoiceAgentListItem[]> => {
  const response = await floConsoleService.voiceAgentService.listAllVoiceAgents();
  if (response.data?.meta?.status === 'success' && response.data.data?.voice_agents) {
    return response.data.data.voice_agents;
  }
  return [];
};

const getVoiceAgentQueryFn = async (agentId: string): Promise<VoiceAgent | null> => {
  const response = await floConsoleService.voiceAgentService.getVoiceAgent(agentId);
  if (response.data?.data) {
    return response.data.data;
  }
  return null;
};

export const useGetVoiceAgents = (appId: string | undefined): UseQueryResult<VoiceAgentListItem[], Error> => {
  return useQueryInit(getVoiceAgentsKey(appId || ''), getVoiceAgentsQueryFn, !!appId);
};

export const useGetVoiceAgent = (
  appId: string | undefined,
  agentId: string | undefined
): UseQueryResult<VoiceAgent | null, Error> => {
  return useQueryInit(
    getVoiceAgentKey(appId || '', agentId || ''),
    () => getVoiceAgentQueryFn(agentId!),
    !!appId && !!agentId
  );
};

// Writes

/**
 * Creates the agent, then attaches the tools picked before it existed. A tool that fails to attach doesn't fail
 * the create; the result counts them so the caller can say so.
 */
export const useCreateVoiceAgent = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: async ({
      data,
      tools = [],
    }: {
      data: CreateVoiceAgentRequest;
      tools?: { toolId: string; isEnabled: boolean }[];
    }) => {
      const response = await floConsoleService.voiceAgentService.createVoiceAgent(data);
      const voiceAgentId = response.data?.data?.voice_agent_id;
      let failedToolCount = 0;
      if (voiceAgentId && tools.length > 0) {
        const results = await Promise.allSettled(
          tools.map(({ toolId, isEnabled }) =>
            floConsoleService.toolService.attachToolToAgent(voiceAgentId, {
              tool_id: toolId,
              is_enabled: isEnabled,
              priority: 0,
            })
          )
        );
        failedToolCount = results.filter((result) => result.status === 'rejected').length;
      }
      return { voiceAgentId, failedToolCount };
    },
    successMessage: 'Voice agent created successfully',
    errorMessage: 'Failed to create voice agent',
    invalidate: () => (appId ? [getVoiceAgentsKey(appId), getVoiceAgentToolsKey(appId)] : []),
  });

export const useUpdateVoiceAgent = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ agentId, data }: { agentId: string; data: Partial<UpdateVoiceAgentRequest> }) =>
      floConsoleService.voiceAgentService.updateVoiceAgent(agentId, data),
    successMessage: 'Voice agent updated successfully',
    errorMessage: 'Failed to update voice agent',
    invalidate: ({ agentId }) => (appId ? [getVoiceAgentsKey(appId), getVoiceAgentKey(appId, agentId)] : []),
  });

export const useDeleteVoiceAgent = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (agentId: string) => floConsoleService.voiceAgentService.deleteVoiceAgent(agentId),
    successMessage: 'Voice agent deleted successfully',
    errorMessage: 'Failed to delete voice agent',
    invalidate: () => [appId && getVoiceAgentsKey(appId)],
  });
