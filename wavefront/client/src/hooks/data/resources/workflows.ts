import floConsoleService from '@app/api';
import { Workflow, WorkflowListItem } from '@app/types/workflow';
import { EntityVersion } from '@app/types/version';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { savedVersionMessage } from './agents';
import { useResourceMutation } from './use-resource-mutation';
import { getWorkflowKey, getWorkflowsKey, getWorkflowVersionsKey } from '../query-keys';

// Reads

const getWorkflowsQueryFn = async (namespace?: string): Promise<WorkflowListItem[]> => {
  const response = await floConsoleService.workflowService.listWorkflows(namespace);
  if (response.data?.meta?.status === 'success' && response.data.data?.data) {
    return response.data.data.data.workflows;
  }
  return [];
};

const getWorkflowVersionsQueryFn = async (workflowId: string): Promise<EntityVersion[]> => {
  const response = await floConsoleService.workflowService.listWorkflowVersions(workflowId);
  if (response.data?.meta?.status === 'success' && response.data.data?.data) {
    return response.data.data.data.versions;
  }
  return [];
};

/** One workflow at `version`, or at its current version when that's left out. */
const getWorkflowQueryFn = async (workflowId: string, version?: number): Promise<Workflow | null> => {
  const response = await floConsoleService.workflowService.getWorkflow(workflowId, version);
  const data = response.data?.meta?.status === 'success' ? response.data.data?.data : undefined;
  if (!data) return null;
  return {
    id: data.id,
    name: data.name,
    namespace: data.namespace,
    created_at: data.created_at,
    updated_at: data.updated_at,
    yaml_content: data.yaml_content || '',
    version: data.version,
    current_version: data.current_version,
  };
};

export const useGetWorkflow = (
  appId: string | undefined,
  workflowId: string | undefined,
  version?: number
): UseQueryResult<Workflow | null, Error> => {
  return useQueryInit(
    getWorkflowKey(appId || '', workflowId || '', version),
    () => getWorkflowQueryFn(workflowId!, version),
    !!appId && !!workflowId
  );
};

export const useGetWorkflows = (
  appId: string | undefined,
  namespace?: string
): UseQueryResult<WorkflowListItem[], Error> => {
  return useQueryInit(getWorkflowsKey(appId || '', namespace), () => getWorkflowsQueryFn(namespace), !!appId);
};

export const useGetWorkflowVersions = (
  appId: string | undefined,
  workflowId: string | undefined
): UseQueryResult<EntityVersion[], Error> => {
  return useQueryInit(
    getWorkflowVersionsKey(appId || '', workflowId || ''),
    () => getWorkflowVersionsQueryFn(workflowId!),
    !!appId && !!workflowId
  );
};

// Writes

export const usePromoteWorkflowVersion = (appId: string | undefined, workflowId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ workflowId, version }: { workflowId: string; version: number }) =>
      floConsoleService.workflowService.promoteWorkflowVersion(workflowId, version),
    successMessage: 'Version promoted successfully',
    errorMessage: 'Failed to promote version',
    invalidate: () =>
      appId && workflowId
        ? [getWorkflowVersionsKey(appId, workflowId), getWorkflowKey(appId, workflowId), getWorkflowsKey(appId)]
        : [],
  });

export const useDeleteWorkflowVersion = (appId: string | undefined, workflowId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ workflowId, version }: { workflowId: string; version: number }) =>
      floConsoleService.workflowService.deleteWorkflowVersion(workflowId, version),
    successMessage: 'Version deleted successfully',
    errorMessage: 'Failed to delete version',
    invalidate: () =>
      appId && workflowId ? [getWorkflowVersionsKey(appId, workflowId), getWorkflowKey(appId, workflowId)] : [],
  });

/** No success toast: the editor reports it once the new workflow is open. */
export const useCreateWorkflow = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({
      workflowId,
      yamlContent,
      namespace,
    }: {
      workflowId: string;
      yamlContent: string;
      namespace?: string;
    }) => floConsoleService.workflowService.createWorkflow(workflowId, yamlContent, namespace),
    errorMessage: 'Failed to create workflow',
    invalidate: () => [appId && getWorkflowsKey(appId)],
  });

export const useUpdateWorkflow = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({
      workflowId,
      yamlContent,
      version,
      createNewVersion = false,
    }: {
      workflowId: string;
      yamlContent: string;
      version?: number;
      createNewVersion?: boolean;
    }) => floConsoleService.workflowService.updateWorkflow(workflowId, yamlContent, version, createNewVersion),
    successMessage: (_, { createNewVersion }) => savedVersionMessage('Workflow', createNewVersion),
    errorMessage: 'Failed to update workflow',
    invalidate: ({ workflowId }) =>
      appId
        ? [getWorkflowVersionsKey(appId, workflowId), getWorkflowKey(appId, workflowId), getWorkflowsKey(appId)]
        : [],
  });

export const useDeleteWorkflow = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (workflowId: string) => floConsoleService.workflowService.deleteWorkflow(workflowId),
    successMessage: 'Workflow deleted successfully',
    errorMessage: 'Failed to delete workflow',
    invalidate: () => [appId && getWorkflowsKey(appId)],
  });
