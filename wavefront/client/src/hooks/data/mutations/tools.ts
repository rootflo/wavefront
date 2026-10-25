import floConsoleService from '@app/api';
import { CreateToolRequest, UpdateToolRequest } from '@app/types/tool';
import { getAgentToolsKey, getVoiceAgentToolKey, getVoiceAgentToolsKey } from '../query-keys';
import { useResourceMutation } from './use-resource-mutation';

export const useCreateTool = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (data: CreateToolRequest) => floConsoleService.toolService.createTool(data),
    successMessage: 'Tool created successfully',
    errorMessage: 'Failed to create tool',
    invalidate: () => [appId && getVoiceAgentToolsKey(appId)],
  });

export const useUpdateTool = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ toolId, data }: { toolId: string; data: UpdateToolRequest }) =>
      floConsoleService.toolService.updateTool(toolId, data),
    successMessage: 'Tool updated successfully',
    errorMessage: 'Failed to update tool',
    invalidate: ({ toolId }) => (appId ? [getVoiceAgentToolsKey(appId), getVoiceAgentToolKey(appId, toolId)] : []),
  });

export const useDeleteTool = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (toolId: string) => floConsoleService.toolService.deleteTool(toolId),
    successMessage: 'Tool deleted successfully',
    errorMessage: 'Failed to delete tool',
    invalidate: () => [appId && getVoiceAgentToolsKey(appId)],
  });

/** Attaching and detaching change both the agent's tool list and each tool's usage. */
const agentToolKeys = (appId: string | undefined, agentId: string) =>
  appId ? [getAgentToolsKey(appId, agentId), getVoiceAgentToolsKey(appId)] : [];

export const useAttachToolToAgent = (appId: string | undefined, agentId: string | undefined) =>
  useResourceMutation({
    mutationFn: (toolId: string) =>
      floConsoleService.toolService.attachToolToAgent(agentId!, { tool_id: toolId, is_enabled: true, priority: 0 }),
    successMessage: 'Tool attached successfully',
    errorMessage: 'Failed to attach tool',
    invalidate: () => (agentId ? agentToolKeys(appId, agentId) : []),
  });

export const useDetachToolFromAgent = (appId: string | undefined, agentId: string | undefined) =>
  useResourceMutation({
    mutationFn: (toolId: string) => floConsoleService.toolService.detachToolFromAgent(agentId!, toolId),
    successMessage: 'Tool detached successfully',
    errorMessage: 'Failed to detach tool',
    invalidate: () => (agentId ? agentToolKeys(appId, agentId) : []),
  });

export const useSetAgentToolEnabled = (appId: string | undefined, agentId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ toolId, enabled }: { toolId: string; enabled: boolean }) =>
      floConsoleService.toolService.updateAgentTool(agentId!, toolId, { is_enabled: enabled }),
    successMessage: (_, { enabled }) => `Tool ${enabled ? 'enabled' : 'disabled'} successfully`,
    errorMessage: 'Failed to toggle tool',
    invalidate: () => [appId && agentId && getAgentToolsKey(appId, agentId)],
  });
