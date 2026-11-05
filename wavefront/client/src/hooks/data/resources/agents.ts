import floConsoleService from '@app/api';
import { AgentApi, AgentListItem } from '@app/types/agent';
import { EntityVersion } from '@app/types/version';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import { getAgentsKey, getAgentKey, getAgentVersionsKey } from '../query-keys';

// Reads

const getAgentsQueryFn = async (namespace?: string): Promise<AgentListItem[]> => {
  const response = await floConsoleService.agentService.listAgents(namespace);
  if (response.data?.meta?.status === 'success' && response.data.data?.data) {
    return response.data.data.data.agents;
  }
  return [];
};

const getAgentQueryFn = async (agentId: string, version?: number): Promise<AgentApi | null> => {
  const response = await floConsoleService.agentService.getAgent(agentId, version);
  if (response.data?.data?.data) {
    return {
      id: response.data.data.data.id,
      name: response.data.data.data.name,
      namespace: response.data.data.data.namespace,
      created_at: response.data.data.data.created_at,
      updated_at: response.data.data.data.updated_at,
      yaml_content: response.data.data.data.yaml_content || '',
      version: response.data.data.data.version,
      current_version: response.data.data.data.current_version,
    };
  }
  return null;
};

const getAgentVersionsQueryFn = async (agentId: string): Promise<EntityVersion[]> => {
  const response = await floConsoleService.agentService.listAgentVersions(agentId);
  if (response.data?.meta?.status === 'success' && response.data.data?.data) {
    return response.data.data.data.versions;
  }
  return [];
};

export const useGetAgents = (appId: string | undefined, namespace?: string): UseQueryResult<AgentListItem[], Error> => {
  return useQueryInit(getAgentsKey(appId || '', namespace), () => getAgentsQueryFn(namespace), !!appId);
};

export const useGetAgent = (
  appId: string | undefined,
  agentId: string | undefined,
  version?: number
): UseQueryResult<AgentApi | null, Error> => {
  return useQueryInit(
    getAgentKey(appId || '', agentId || '', version),
    () => getAgentQueryFn(agentId!, version),
    !!appId && !!agentId
  );
};

export const useGetAgentVersions = (
  appId: string | undefined,
  agentId: string | undefined
): UseQueryResult<EntityVersion[], Error> => {
  return useQueryInit(
    getAgentVersionsKey(appId || '', agentId || ''),
    () => getAgentVersionsQueryFn(agentId!),
    !!appId && !!agentId
  );
};

// Writes

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
