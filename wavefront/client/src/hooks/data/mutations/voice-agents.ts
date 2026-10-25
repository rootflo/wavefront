import floConsoleService from '@app/api';
import { CreateVoiceAgentRequest, UpdateVoiceAgentRequest } from '@app/types/voice-agent';
import { getVoiceAgentKey, getVoiceAgentsKey, getVoiceAgentToolsKey } from '../query-keys';
import { useResourceMutation } from './use-resource-mutation';

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
