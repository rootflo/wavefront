import floConsoleService from '@app/api';
import BulkDownloadDialog from '@app/components/BulkDownloadDialog';
import BulkUploadDialog, { MAX_BULK_UPLOAD_FILES } from '@app/components/BulkUploadDialog';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { ErrorBanner } from '@app/components/Banner';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { useGetNamespaces, useGetWorkflows } from '@app/hooks';
import { getWorkflowsKey } from '@app/hooks/data/query-keys';
import { copyToClipboard, createZipBlob, downloadBlobFile, downloadTextFile, getYamlFilename } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { WorkflowListItem } from '@app/types/workflow';
import { useQueryClient } from '@tanstack/react-query';
import { Copy, Download, Trash2 } from 'lucide-react';
import React, { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import CreateWorkflowDialog from './CreateWorkflowDialog';
import { parseUploadedWorkflow } from './workflow-utils';

const formatCreatedAt = (value?: string) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString();
};

const ALL_NAMESPACES = '__all__';

const WorkflowManagement: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();
  const [searchTerm, setSearchTerm] = useState('');
  const [namespace, setNamespace] = useState('');
  const [deleteItem, setDeleteItem] = useState<WorkflowListItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [bulkDownloadOpen, setBulkDownloadOpen] = useState(false);
  const [bulkUploadOpen, setBulkUploadOpen] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [bulkError, setBulkError] = useState('');

  const { data: workflows = [], isLoading: loading } = useGetWorkflows(appId, namespace || undefined);
  const { data: namespaces = [] } = useGetNamespaces(appId);

  const filteredWorkflows = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    const filtered = term
      ? workflows.filter(
          (workflow) =>
            workflow.name.toLowerCase().includes(term) ||
            workflow.id.toLowerCase().includes(term) ||
            workflow.namespace.toLowerCase().includes(term)
        )
      : workflows;

    return [...filtered].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
  }, [workflows, searchTerm]);

  const handleCopyId = async (id: string) => {
    const copied = await copyToClipboard(id);
    if (copied) {
      notifySuccess('Copied ID to clipboard');
    } else {
      notifyError('Failed to copy ID');
    }
  };

  const fetchWorkflowYaml = async (workflow: WorkflowListItem) => {
    const response = await floConsoleService.workflowService.getWorkflow(workflow.id);
    const data = response.data?.data?.data;
    if (!data?.yaml_content) return null;
    return {
      filename: getYamlFilename(workflow.name),
      content: data.yaml_content,
    };
  };

  const handleWorkflowDownload = async (workflow: WorkflowListItem) => {
    setDownloadingId(workflow.id);
    try {
      const file = await fetchWorkflowYaml(workflow);
      if (!file) {
        notifyError('Failed to download workflow');
        return;
      }
      downloadTextFile(file.filename, file.content);
    } catch {
      notifyError('Failed to download workflow');
    } finally {
      setDownloadingId(null);
    }
  };

  const handleWorkflowDownloadMany = async (selected: WorkflowListItem[]) => {
    const files: { filename: string; content: string }[] = [];
    const failed: string[] = [];
    for (const workflow of selected) {
      const filename = getYamlFilename(workflow.name);
      try {
        const file = await fetchWorkflowYaml(workflow);
        if (file) files.push(file);
        else failed.push(filename);
      } catch {
        failed.push(filename);
      }
    }

    if (files.length === 0) {
      setBulkError(`Failed to download workflows: ${failed.join(', ')}`);
      return;
    }

    downloadBlobFile('workflows.zip', createZipBlob(files));
    setBulkError(failed.length > 0 ? `Failed to download: ${failed.join(', ')}` : '');
  };

  const handleWorkflowUploadMany = async (files: { name: string; content: string }[]) => {
    let created = 0;
    const failed: string[] = [];
    const uploadNamespace = namespace || 'default';
    for (const file of files) {
      try {
        const response = await floConsoleService.workflowService.createWorkflow(
          file.name,
          file.content,
          uploadNamespace
        );
        if (response.data?.meta?.status === 'failure') {
          failed.push(file.name);
        } else {
          created += 1;
        }
      } catch {
        failed.push(file.name);
      }
    }

    queryClient.invalidateQueries({
      queryKey: getWorkflowsKey(appId || ''),
    });

    if (created > 0) {
      notifySuccess(`Created ${created} ${created === 1 ? 'workflow' : 'workflows'}`);
    }
    setBulkError(failed.length > 0 ? `Failed to create workflows: ${failed.join(', ')}` : '');
  };

  const handleDelete = async () => {
    if (!deleteItem) return;

    setDeleting(true);
    try {
      await floConsoleService.workflowService.deleteWorkflow(deleteItem.id);
      notifySuccess('Workflow deleted successfully');
      queryClient.invalidateQueries({
        queryKey: getWorkflowsKey(appId || '', namespace || undefined),
      });
      setDeleteItem(null);
    } catch {
      notifyError('Failed to delete workflow');
    } finally {
      setDeleting(false);
    }
  };

  const handleCreateSuccess = () => {
    queryClient.invalidateQueries({
      queryKey: getWorkflowsKey(appId || '', namespace || undefined),
    });
    setCreateDialogOpen(false);
  };

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden">
      <div className="mb-8 flex shrink-0 items-center justify-end gap-3">
        <Select
          value={namespace || ALL_NAMESPACES}
          onValueChange={(value) => setNamespace(value === ALL_NAMESPACES ? '' : value)}
        >
          <SelectTrigger className="w-48 cursor-pointer">
            <SelectValue placeholder="All Namespaces" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_NAMESPACES}>All Namespaces</SelectItem>
            {namespaces.map((ns) => (
              <SelectItem key={ns.name} value={ns.name}>
                {ns.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          type="text"
          placeholder="Search"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-[180px]"
        />
        <Button variant="outline" onClick={() => setBulkDownloadOpen(true)} disabled={workflows.length === 0}>
          Download
        </Button>
        <Button variant="outline" onClick={() => setBulkUploadOpen(true)}>
          Upload
        </Button>
        <Button onClick={() => setCreateDialogOpen(true)}>Create Workflow</Button>
      </div>

      {bulkError ? <ErrorBanner message={bulkError} onDismiss={() => setBulkError('')} /> : null}

      {loading ? (
        <p className="frost-text-muted text-sm">Loading workflows...</p>
      ) : filteredWorkflows.length === 0 ? (
        <div className="mt-10 flex justify-center">
          <EmptyStateCard
            title="No workflows found"
            description="Get started by creating your first workflow"
            actionText="Create Workflow"
            onActionClick={() => setCreateDialogOpen(true)}
          />
        </div>
      ) : (
        <div className="frost-table-panel ring-frost-border min-h-0 flex-1 overflow-auto rounded-xl border ring-1">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>ID</TableHead>
                <TableHead>Namespace</TableHead>
                <TableHead>Version</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredWorkflows.map((workflow) => (
                <TableRow
                  key={workflow.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/apps/${appId}/workflows/${workflow.id}`)}
                >
                  <TableCell className="max-w-[220px] truncate font-medium" title={workflow.name}>
                    {workflow.name}
                  </TableCell>
                  <TableCell className="max-w-[240px]" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center gap-1">
                      <span className="truncate font-mono text-xs" title={workflow.id}>
                        {workflow.id}
                      </span>
                      <Button variant="ghost" size="sm" title="Copy ID" onClick={() => void handleCopyId(workflow.id)}>
                        <Copy className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                  <TableCell className="frost-text-muted">{workflow.namespace || '—'}</TableCell>
                  <TableCell className="frost-text-muted">
                    {workflow.current_version !== undefined ? `v${workflow.current_version}` : '—'}
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap">{formatCreatedAt(workflow.created_at)}</TableCell>
                  <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                    <div className="flex items-center justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        title="Download"
                        loading={downloadingId === workflow.id}
                        onClick={() => void handleWorkflowDownload(workflow)}
                      >
                        <Download className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="sm" title="Delete" onClick={() => setDeleteItem(workflow)}>
                        <Trash2 className="h-4 w-4 text-red-600" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <DeleteConfirmationDialog
        isOpen={!!deleteItem}
        title="Delete Workflow"
        message={`Are you sure you want to delete "${deleteItem?.name}"? This action cannot be undone.`}
        onConfirm={handleDelete}
        onCancel={() => setDeleteItem(null)}
        loading={deleting}
      />

      {appId && (
        <CreateWorkflowDialog
          isOpen={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          appId={appId}
          onSuccess={handleCreateSuccess}
        />
      )}

      <BulkDownloadDialog
        isOpen={bulkDownloadOpen}
        onOpenChange={setBulkDownloadOpen}
        title="Download Workflows"
        description="Select workflows to download. Each file is named after the workflow."
        emptyLabel="No workflows available"
        items={workflows}
        getItemId={(workflow) => workflow.id}
        getItemLabel={(workflow) => getYamlFilename(workflow.name)}
        onDownload={handleWorkflowDownloadMany}
      />
      <BulkUploadDialog
        isOpen={bulkUploadOpen}
        onOpenChange={setBulkUploadOpen}
        title="Upload Workflows"
        description={`Upload up to ${MAX_BULK_UPLOAD_FILES} YAML files. The file name (without .yaml) is used as the workflow name. Only valid workflow YAML files are accepted. Files whose name already exists will be skipped.`}
        parseFile={(filename, content, seen) => {
          const existingNames = new Set(
            workflows.flatMap((workflow) => [workflow.name.trim().toLowerCase(), workflow.id.trim().toLowerCase()])
          );
          const parsed = parseUploadedWorkflow(filename, content, existingNames, seen);
          return { ...parsed, label: parsed.name };
        }}
        onUpload={(files) => handleWorkflowUploadMany(files.map(({ name, content }) => ({ name, content })))}
      />
    </div>
  );
};

export default WorkflowManagement;
