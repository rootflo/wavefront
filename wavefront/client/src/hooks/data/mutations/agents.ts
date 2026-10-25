import floConsoleService from '@app/api';
import { getAgentKey, getAgentsKey, getAgentVersionsKey } from '../query-keys';
import { useResourceMutation } from './use-resource-mutation';

export const useDeleteAgent = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (agentId: string) => floConsoleService.agentService.deleteAgent(agentId),
    successMessage: 'Agent deleted successfully',
    errorMessage: 'Failed to delete agent',
    invalidate: () => [appId && getAgentsKey(appId)],
  });

export const usePromoteAgentVersion = (appId: string | undefined, agentId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ agentId, version }: { agentId: string; version: number }) =>
      floConsoleService.agentService.promoteAgentVersion(agentId, version),
    successMessage: 'Version promoted successfully',
    errorMessage: 'Failed to promote version',
    invalidate: () =>
      appId && agentId ? [getAgentVersionsKey(appId, agentId), getAgentKey(appId, agentId), getAgentsKey(appId)] : [],
  });

export const useDeleteAgentVersion = (appId: string | undefined, agentId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ agentId, version }: { agentId: string; version: number }) =>
      floConsoleService.agentService.deleteAgentVersion(agentId, version),
    successMessage: 'Version deleted successfully',
    errorMessage: 'Failed to delete version',
    invalidate: () => (appId && agentId ? [getAgentVersionsKey(appId, agentId), getAgentKey(appId, agentId)] : []),
  });

type SavedYaml = { yamlContent: string; version?: number; createNewVersion?: boolean };

/** Shared by agents and workflows: saving as a new version doesn't make it live. */
export const savedVersionMessage = (kind: 'Agent' | 'Workflow', createNewVersion?: boolean) =>
  createNewVersion
    ? 'New version created (not promoted — promote it from Versions to make it live)'
    : `${kind} updated successfully`;

export const useCreateAgent = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ agentId, yamlContent, namespace }: { agentId: string; yamlContent: string; namespace?: string }) =>
      floConsoleService.agentService.createAgent(agentId, yamlContent, namespace),
    successMessage: 'Agent created successfully',
    errorMessage: 'Failed to create agent',
    invalidate: () => [appId && getAgentsKey(appId)],
  });

export const useUpdateAgent = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ agentId, yamlContent, version, createNewVersion = false }: SavedYaml & { agentId: string }) =>
      floConsoleService.agentService.updateAgent(agentId, yamlContent, version, createNewVersion),
    successMessage: (_, { createNewVersion }) => savedVersionMessage('Agent', createNewVersion),
    errorMessage: 'Failed to update agent',
    invalidate: ({ agentId }) =>
      appId ? [getAgentKey(appId, agentId), getAgentVersionsKey(appId, agentId), getAgentsKey(appId)] : [],
  });
