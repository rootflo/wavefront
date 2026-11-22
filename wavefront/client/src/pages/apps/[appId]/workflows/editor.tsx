import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { Input } from '@app/components/ui/input';
import { AGENT_ID_PATTERN, AGENT_ID_PATTERN_MESSAGE } from '@app/constants/workflow-builder';
import { useCreateWorkflow, useGetWorkflowVersions } from '@app/hooks';
import { getWorkflowVersionsKey } from '@app/hooks/data/query-keys';
import { useValidateWorkflowYaml } from '@app/hooks/data/yaml-validation-hooks';
import { useBeforeUnloadGuard } from '@app/hooks/use-before-unload-guard';
import { useNotifyStore } from '@app/store';
import { Workflow } from '@app/types/workflow';
import { useQueryClient } from '@tanstack/react-query';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router';
import { DEFAULT_WORKFLOW_YAML } from './defaultWorkflowYaml';
import EditorVersionSelect from './EditorVersionSelect';
import WorkflowEditorWorkspace from './WorkflowEditorWorkspace';
import { broadcastWorkflowUpdated, toProblems, useWorkflowDraftSave } from './useWorkflowDraftSave';
import type { Problem } from '@app/components/WorkflowBuilder/ProblemsPanel';

const DEFAULT_NAMESPACE = 'default';

// Standalone, full-screen workflow editor that always opens in its own browser tab.
// /apps/:app/workflows/new creates a workflow; /apps/:app/workflows/:id/editor edits one.
const WorkflowEditorPage: React.FC = () => {
  const { app: appId, id } = useParams<{ app: string; id: string }>();
  const isCreate = !id;
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { notifySuccess } = useNotifyStore();
  const createWorkflow = useCreateWorkflow(appId);
  const queryClient = useQueryClient();
  const versionParam = searchParams.get('version');
  const selectedVersion = versionParam ? Number(versionParam) : undefined;

  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [savedYaml, setSavedYaml] = useState(isCreate ? DEFAULT_WORKFLOW_YAML : '');
  const [draftYaml, setDraftYaml] = useState(isCreate ? DEFAULT_WORKFLOW_YAML : '');
  const draftYamlRef = useRef(draftYaml);
  draftYamlRef.current = draftYaml;
  const [loadError, setLoadError] = useState<string | null>(null);
  const [discardConfirmOpen, setDiscardConfirmOpen] = useState(false);
  // Version the user picked while the draft had unsaved edits; applied once they confirm
  const [pendingVersion, setPendingVersion] = useState<number | null>(null);
  const [loadingWorkflow, setLoadingWorkflow] = useState(false);
  const loadRequestRef = useRef(0);

  const { data: workflowVersions = [] } = useGetWorkflowVersions(appId, id);

  // Create mode only
  const [workflowId, setWorkflowId] = useState('');
  const [namespace, setNamespace] = useState(DEFAULT_NAMESPACE);
  const [fieldErrors, setFieldErrors] = useState<{ workflowId?: string; namespace?: string }>({});
  const [creating, setCreating] = useState(false);
  const [createErrors, setCreateErrors] = useState<Problem[]>([]);
  const validateYaml = useValidateWorkflowYaml();

  const loadWorkflow = useCallback(async () => {
    if (!id) return;
    const requestId = ++loadRequestRef.current;
    try {
      const response = await floConsoleService.workflowService.getWorkflow(id, selectedVersion);
      // A newer load (e.g. another version picked meanwhile) supersedes this one
      if (requestId !== loadRequestRef.current) return;
      const data = response.data?.meta?.status === 'success' ? response.data.data?.data : undefined;
      if (!data) {
        setLoadError('Workflow not found');
        return;
      }
      setWorkflow({
        id: data.id,
        name: data.name,
        namespace: data.namespace,
        created_at: data.created_at,
        updated_at: data.updated_at,
        yaml_content: data.yaml_content || '',
        version: data.version,
        current_version: data.current_version,
      });
      setSavedYaml(data.yaml_content || '');
      setLoadError(null);
      return data.yaml_content || '';
    } catch (error) {
      console.error('Error loading workflow:', error);
      setLoadError('Failed to load workflow');
    }
  }, [id, selectedVersion]);

  useEffect(() => {
    if (!id) return;
    setLoadingWorkflow(true);
    loadWorkflow()
      .then((yaml) => {
        if (yaml !== undefined) setDraftYaml(yaml);
      })
      .finally(() => setLoadingWorkflow(false));
  }, [id, loadWorkflow]);

  useEffect(() => {
    setCreateErrors([]);
  }, [draftYaml]);

  const isDirty = isCreate
    ? workflowId.trim() !== '' || namespace !== DEFAULT_NAMESPACE || draftYaml !== savedYaml
    : workflow !== null && draftYaml !== savedYaml;
  useBeforeUnloadGuard(isDirty);

  // Version being edited (and overwritten by Save); the server defaults to the current version
  const editingVersion = selectedVersion ?? workflow?.current_version;

  const showVersion = useCallback(
    (version: number) => {
      setPendingVersion(null);
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set('version', String(version));
          return next;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  const handleSaved = useCallback(
    async (createNewVersion: boolean, savedVersion?: number) => {
      if (createNewVersion && savedVersion !== undefined) {
        // Continue on the version that was just created; the draft is exactly what was saved
        setSavedYaml(draftYamlRef.current);
        // Wait for the versions list to include the new version so the selector never shows a blank value
        await queryClient.invalidateQueries({ queryKey: getWorkflowVersionsKey(appId || '', id || '') });
        showVersion(savedVersion);
        return;
      }
      await loadWorkflow();
    },
    [loadWorkflow, showVersion, queryClient, appId, id]
  );

  const { saving, submitAction, validationErrors, dismissValidationErrors, save } = useWorkflowDraftSave({
    appId,
    workflowId: id,
    draftYaml,
    baseVersion: editingVersion,
    onSaved: handleSaved,
  });

  const handleCreate = async () => {
    const trimmedId = workflowId.trim();
    const trimmedNamespace = namespace.trim();
    const errors: typeof fieldErrors = {};
    if (!trimmedId) errors.workflowId = 'Workflow ID is required';
    else if (!AGENT_ID_PATTERN.test(trimmedId)) errors.workflowId = AGENT_ID_PATTERN_MESSAGE;
    if (!trimmedNamespace) errors.namespace = 'Namespace is required';
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;
    if (!draftYaml.trim()) {
      setCreateErrors([{ message: 'YAML content is required' }]);
      return;
    }

    setCreating(true);
    setCreateErrors([]);
    try {
      const validation = await validateYaml.mutateAsync({ yamlContent: draftYaml.trim() }).catch(() => null);
      if (validation && !validation.valid) {
        setCreateErrors(toProblems(validation.errors));
        return;
      }
      const response = await createWorkflow.mutateAsync({
        workflowId: trimmedId,
        yamlContent: draftYaml.trim(),
        namespace: trimmedNamespace,
      });
      const createdId = response.data?.meta?.status === 'success' ? response.data.data?.data?.id : undefined;
      if (createdId) {
        broadcastWorkflowUpdated(createdId);
        notifySuccess('Workflow created successfully');
        // Same tab continues as the editor for the new workflow; nothing is unsaved at this point
        setSavedYaml(draftYaml);
        navigate(`/apps/${appId}/workflows/${createdId}/editor`, { replace: true });
      }
    } catch {
      // useCreateWorkflow has already shown the error
    } finally {
      setCreating(false);
    }
  };

  const closeEditor = () => {
    setDiscardConfirmOpen(false);
    // window.close only works for tabs opened by script; otherwise fall back to the workflow page or list
    window.close();
    navigate(isCreate ? `/apps/${appId}/workflows` : `/apps/${appId}/workflows/${id}`);
  };

  const busy = saving || creating;

  const requestVersionChange = (version: number) => {
    if (version === editingVersion) return;
    if (isDirty) {
      setPendingVersion(version);
      return;
    }
    showVersion(version);
  };

  const requestClose = () => {
    if (busy) return;
    if (isDirty) {
      setDiscardConfirmOpen(true);
      return;
    }
    closeEditor();
  };

  if (loadError) {
    return (
      <div className="bg-background text-muted-foreground flex h-screen w-screen items-center justify-center text-sm">
        {loadError}
      </div>
    );
  }

  const headerFields = isCreate ? (
    <div className="flex items-center gap-3">
      <label className="flex items-center gap-1.5">
        <span className="text-muted-foreground text-[11px] font-medium">ID:</span>
        <Input
          value={workflowId}
          onChange={(e) => {
            setWorkflowId(e.target.value);
            setFieldErrors((prev) => ({ ...prev, workflowId: undefined }));
          }}
          placeholder="workflow-id"
          aria-invalid={Boolean(fieldErrors.workflowId)}
          className="bg-background h-7 w-44 font-mono text-xs"
        />
        {fieldErrors.workflowId && <span className="text-destructive text-[10px]">{fieldErrors.workflowId}</span>}
      </label>
      <label className="flex items-center gap-1.5">
        <span className="text-muted-foreground text-[11px] font-medium">Namespace:</span>
        <Input
          value={namespace}
          onChange={(e) => {
            setNamespace(e.target.value);
            setFieldErrors((prev) => ({ ...prev, namespace: undefined }));
          }}
          placeholder={DEFAULT_NAMESPACE}
          aria-invalid={Boolean(fieldErrors.namespace)}
          className="bg-background h-7 w-32 font-mono text-xs"
        />
        {fieldErrors.namespace && <span className="text-destructive text-[10px]">{fieldErrors.namespace}</span>}
      </label>
    </div>
  ) : workflowVersions.length > 0 ? (
    <EditorVersionSelect
      versions={workflowVersions}
      value={editingVersion}
      disabled={busy || loadingWorkflow}
      onChange={requestVersionChange}
    />
  ) : undefined;

  return (
    <div className="bg-background fixed inset-0 flex h-screen w-screen flex-col overflow-hidden">
      <WorkflowEditorWorkspace
        title={
          <h1 className="text-foreground text-xs leading-none font-semibold">
            {isCreate ? 'Create Workflow' : 'Edit Workflow Configuration'}
          </h1>
        }
        subtitle={
          isCreate ? (
            'Studio Builder'
          ) : (
            <>
              {workflow?.name || id} {workflow?.namespace && `(${workflow.namespace})`}
            </>
          )
        }
        headerFields={headerFields}
        yaml={draftYaml}
        onYamlChange={setDraftYaml}
        saving={busy || loadingWorkflow}
        submitAction={submitAction}
        validationErrors={isCreate ? createErrors : validationErrors}
        saveHint={editingVersion !== undefined ? `Saves over v${editingVersion}` : undefined}
        onDismissValidationErrors={isCreate ? () => setCreateErrors([]) : dismissValidationErrors}
        cancelLabel="Close"
        onCancel={requestClose}
        onCreate={isCreate ? handleCreate : undefined}
        onSave={
          isCreate
            ? undefined
            : (createNewVersion) => {
                if (workflow) save(createNewVersion);
              }
        }
      />

      <DeleteConfirmationDialog
        isOpen={discardConfirmOpen}
        title="Discard unsaved changes?"
        message={
          isCreate
            ? 'This workflow has not been created yet. Closing the editor will discard it.'
            : 'You have unsaved changes to this workflow. Closing the editor will discard them.'
        }
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        onConfirm={closeEditor}
        onCancel={() => setDiscardConfirmOpen(false)}
      />

      <DeleteConfirmationDialog
        isOpen={pendingVersion !== null}
        title="Discard unsaved changes?"
        message={`Switching to v${pendingVersion} will replace your unsaved edits with that version.`}
        confirmLabel="Discard and switch"
        cancelLabel="Keep editing"
        onConfirm={() => {
          if (pendingVersion !== null) showVersion(pendingVersion);
        }}
        onCancel={() => setPendingVersion(null)}
      />
    </div>
  );
};

export default WorkflowEditorPage;
