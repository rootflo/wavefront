import floConsoleService from '@app/api';
import {
  ToolDetails,
  VoiceAgentTool,
  VoiceAgentToolWithAssociation,
  CreateToolRequest,
  UpdateToolRequest,
} from '@app/types/tool';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import { getToolsKey, getVoiceAgentToolsKey, getVoiceAgentToolKey, getAgentToolsKey } from '../query-keys';

// Reads

const getToolsQueryFn = async (): Promise<ToolDetails[]> => {
  const response = await floConsoleService.toolService.getToolNamesAndDetails();
  if (response.data?.data?.data?.tool_details && Array.isArray(response.data.data.data.tool_details)) {
    return response.data.data.data.tool_details;
  }
  return [];
};

const getVoiceAgentToolsQueryFn = async (): Promise<VoiceAgentTool[]> => {
  const response = await floConsoleService.toolService.listTools();
  if (response.data?.meta?.status === 'success' && response.data.data?.tools) {
    return response.data.data.tools;
  }
  return [];
};

const getVoiceAgentToolQueryFn = async (toolId: string): Promise<VoiceAgentTool | null> => {
  const response = await floConsoleService.toolService.getTool(toolId);
  if (response.data?.meta?.status === 'success' && response.data.data) {
    return response.data.data;
  }
  return null;
};

const getAgentToolsQueryFn = async (agentId: string): Promise<VoiceAgentToolWithAssociation[]> => {
  const response = await floConsoleService.toolService.getAgentTools(agentId);
  if (response.data?.meta?.status === 'success' && response.data.data?.tools) {
    return response.data.data.tools;
  }
  return [];
};

export const useGetTools = (appId: string | undefined): UseQueryResult<ToolDetails[], Error> => {
  return useQueryInit(getToolsKey(appId || ''), getToolsQueryFn, !!appId);
};

export const useGetVoiceAgentTools = (appId: string | undefined): UseQueryResult<VoiceAgentTool[], Error> => {
  return useQueryInit(getVoiceAgentToolsKey(appId || ''), getVoiceAgentToolsQueryFn, !!appId);
};

export const useGetVoiceAgentTool = (
  appId: string | undefined,
  toolId: string | undefined
): UseQueryResult<VoiceAgentTool | null, Error> => {
  return useQueryInit(
    getVoiceAgentToolKey(appId || '', toolId || ''),
    () => getVoiceAgentToolQueryFn(toolId!),
    !!appId && !!toolId
  );
};

export const useGetAgentTools = (
  appId: string | undefined,
  agentId: string | undefined
): UseQueryResult<VoiceAgentToolWithAssociation[], Error> => {
  return useQueryInit(
    getAgentToolsKey(appId || '', agentId || ''),
    () => getAgentToolsQueryFn(agentId!),
    !!appId && !!agentId
  );
};

// Writes

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
