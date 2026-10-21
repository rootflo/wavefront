import floConsoleService from '@app/api';
import { getWorkflowVersionsKey } from '@app/hooks/data/query-keys';
import { useValidateWorkflowYaml } from '@app/hooks/data/yaml-validation-hooks';
import { useNotifyStore } from '@app/store';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useState } from 'react';
import type { Problem } from '@app/components/WorkflowBuilder/ProblemsPanel';

export type WorkflowSaveAction = 'save' | 'new';

// Server validation errors as panel items: the message leads, the YAML path is shown as its location
export const toProblems = (errors: { path: string; message: string }[]): Problem[] =>
  errors.map((e) => ({ message: e.message, location: e.path || undefined }));

// Other tabs showing the same workflow listen on this channel to reload after a save
export const WORKFLOW_UPDATED_CHANNEL = 'workflow-updated';

export interface WorkflowUpdatedMessage {
  workflowId: string;
}

// Tell other tabs (workflow list, workflow page) that a workflow was created or saved
export const broadcastWorkflowUpdated = (workflowId: string) => {
  if (typeof BroadcastChannel === 'undefined') return;
  const channel = new BroadcastChannel(WORKFLOW_UPDATED_CHANNEL);
  channel.postMessage({ workflowId } satisfies WorkflowUpdatedMessage);
  channel.close();
};

// Subscribe to workflow updates from other tabs
export const useWorkflowUpdatedListener = (onUpdated: (workflowId: string) => void) => {
  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return;
    const channel = new BroadcastChannel(WORKFLOW_UPDATED_CHANNEL);
    channel.onmessage = (event: MessageEvent<WorkflowUpdatedMessage>) => {
      if (event.data?.workflowId) onUpdated(event.data.workflowId);
    };
    return () => channel.close();
  }, [onUpdated]);
};

interface UseWorkflowDraftSaveOptions {
  appId?: string;
  workflowId?: string;
  draftYaml: string;
  baseVersion?: number;
  // savedVersion is the version the server wrote: the edited one, or the newly created one
  onSaved: (createNewVersion: boolean, savedVersion?: number) => void | Promise<void>;
}

// Validates and saves a workflow draft from the standalone editor tab
export const useWorkflowDraftSave = ({
  appId,
  workflowId,
  draftYaml,
  baseVersion,
  onSaved,
}: UseWorkflowDraftSaveOptions) => {
  const { notifySuccess } = useNotifyStore();
  const queryClient = useQueryClient();
  const validateYaml = useValidateWorkflowYaml();
  const [saving, setSaving] = useState(false);
  const [submitAction, setSubmitAction] = useState<WorkflowSaveAction | null>(null);
  const [validationErrors, setValidationErrors] = useState<Problem[]>([]);

  useEffect(() => {
    setValidationErrors([]);
  }, [draftYaml]);

  const save = useCallback(
    async (createNewVersion: boolean) => {
      if (!workflowId) return;

      setSaving(true);
      setSubmitAction(createNewVersion ? 'new' : 'save');
      setValidationErrors([]);
      try {
        const validation = await validateYaml.mutateAsync({ yamlContent: draftYaml }).catch(() => null);
        if (validation && !validation.valid) {
          setValidationErrors(toProblems(validation.errors));
          return;
        }
        const response = await floConsoleService.workflowService.updateWorkflow(
          workflowId,
          draftYaml,
          baseVersion,
          createNewVersion
        );
        const savedVersion = response.data?.meta?.status === 'success' ? response.data.data?.data?.version : undefined;
        // Refetch versions so version metadata stays in sync.
        queryClient.invalidateQueries({ queryKey: getWorkflowVersionsKey(appId || '', workflowId) });
        await onSaved(createNewVersion, savedVersion);
        broadcastWorkflowUpdated(workflowId);
        notifySuccess(
          createNewVersion
            ? 'New version created (not promoted — promote it from Versions to make it live)'
            : 'Workflow updated successfully'
        );
      } catch (error) {
        console.error('Error updating workflow:', error);
      } finally {
        setSaving(false);
        setSubmitAction(null);
      }
    },
    [appId, workflowId, draftYaml, baseVersion, onSaved, validateYaml, queryClient, notifySuccess]
  );

  const dismissValidationErrors = useCallback(() => setValidationErrors([]), []);

  return { saving, submitAction, validationErrors, dismissValidationErrors, save };
};
