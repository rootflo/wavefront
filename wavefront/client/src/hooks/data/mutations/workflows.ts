import floConsoleService from '@app/api';
import { getWorkflowsKey, getWorkflowVersionsKey } from '../query-keys';
import { savedVersionMessage } from './agents';
import { useResourceMutation } from './use-resource-mutation';

export const usePromoteWorkflowVersion = (appId: string | undefined, workflowId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ workflowId, version }: { workflowId: string; version: number }) =>
      floConsoleService.workflowService.promoteWorkflowVersion(workflowId, version),
    successMessage: 'Version promoted successfully',
    errorMessage: 'Failed to promote version',
    invalidate: () => (appId && workflowId ? [getWorkflowVersionsKey(appId, workflowId), getWorkflowsKey(appId)] : []),
  });

export const useDeleteWorkflowVersion = (appId: string | undefined, workflowId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ workflowId, version }: { workflowId: string; version: number }) =>
      floConsoleService.workflowService.deleteWorkflowVersion(workflowId, version),
    successMessage: 'Version deleted successfully',
    errorMessage: 'Failed to delete version',
    invalidate: () => [appId && workflowId && getWorkflowVersionsKey(appId, workflowId)],
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
    invalidate: ({ workflowId }) => (appId ? [getWorkflowVersionsKey(appId, workflowId), getWorkflowsKey(appId)] : []),
  });

export const useDeleteWorkflow = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (workflowId: string) => floConsoleService.workflowService.deleteWorkflow(workflowId),
    successMessage: 'Workflow deleted successfully',
    errorMessage: 'Failed to delete workflow',
    invalidate: () => [appId && getWorkflowsKey(appId)],
  });
