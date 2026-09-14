import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@app/components/ui/table';
import { useGetWorkflowPipelines, useGetWorkflows } from '@app/hooks';
import { getWorkflowPipelinesKey } from '@app/hooks/data/query-keys';
import { copyToClipboard } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { WorkflowPipelineListItem } from '@app/types/workflow';
import { useQueryClient } from '@tanstack/react-query';
import { Copy, Trash2 } from 'lucide-react';
import React, { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router';
import CreateWorkflowPipelineDialog from './CreateWorkflowPipelineDialog';

const formatCreatedAt = (value?: string) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString();
};

const ALL_WORKFLOWS = '__all__';

const WorkflowPipelinesPage: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();
  const [searchTerm, setSearchTerm] = useState('');
  const [workflow, setWorkflow] = useState('');
  const [deleteItem, setDeleteItem] = useState<WorkflowPipelineListItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  const { data: workflowPipelines = [], isLoading: workflowPipelinesLoading } = useGetWorkflowPipelines(appId);
  const { data: workflows = [] } = useGetWorkflows(appId);

  const workflowNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const item of workflows) {
      map.set(item.id, item.name);
    }
    return map;
  }, [workflows]);

  const filteredWorkflowPipelines = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    const filtered = workflowPipelines.filter((pipeline) => {
      const matchesWorkflow = !workflow || pipeline.workflow_id === workflow;
      if (!matchesWorkflow) return false;
      if (!term) return true;
      const workflowName = (workflowNameById.get(pipeline.workflow_id || '') || '').toLowerCase();
      return (
        pipeline.name.toLowerCase().includes(term) ||
        pipeline.id.toLowerCase().includes(term) ||
        workflowName.includes(term)
      );
    });

    return [...filtered].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
  }, [workflowPipelines, searchTerm, workflow, workflowNameById]);

  const handleCopyId = async (id: string) => {
    const copied = await copyToClipboard(id);
    if (copied) {
      notifySuccess('Copied ID to clipboard');
    } else {
      notifyError('Failed to copy ID');
    }
  };

  const handleDelete = async () => {
    if (!deleteItem) return;

    setDeleting(true);
    try {
      await floConsoleService.workflowService.deleteWorkflowPipeline(deleteItem.id);
      notifySuccess('Workflow pipeline deleted successfully');
      queryClient.invalidateQueries({
        queryKey: getWorkflowPipelinesKey(appId || ''),
      });
      setDeleteItem(null);
    } catch {
      notifyError('Failed to delete workflow pipeline');
    } finally {
      setDeleting(false);
    }
  };

  const handleCreateSuccess = () => {
    queryClient.invalidateQueries({
      queryKey: getWorkflowPipelinesKey(appId || ''),
    });
    setCreateDialogOpen(false);
  };

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden">
      <div className="mb-8 flex shrink-0 items-center justify-end gap-3">
        <Select
          value={workflow || ALL_WORKFLOWS}
          onValueChange={(value) => setWorkflow(value === ALL_WORKFLOWS ? '' : value)}
        >
          <SelectTrigger className="w-48 cursor-pointer">
            <SelectValue placeholder="All Workflows" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_WORKFLOWS}>All Workflows</SelectItem>
            {workflows.map((wf) => (
              <SelectItem key={wf.id} value={wf.id}>
                {wf.name}
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
        <Button onClick={() => setCreateDialogOpen(true)}>Create Pipeline</Button>
      </div>

      {workflowPipelinesLoading ? (
        <p className="text-sm text-gray-500">Loading pipelines...</p>
      ) : filteredWorkflowPipelines.length === 0 ? (
        <div className="mt-10 flex justify-center">
          <EmptyStateCard
            title="No pipelines found"
            description="Get started by creating your first pipeline"
            actionText="Create Pipeline"
            onActionClick={() => setCreateDialogOpen(true)}
          />
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-[#EFF0F1]">
          <Table>
            <TableHeader className="sticky top-0 z-10 bg-white">
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>ID</TableHead>
                <TableHead>Workflow</TableHead>
                <TableHead>Version</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredWorkflowPipelines.map((pipeline) => (
                <TableRow key={pipeline.id}>
                  <TableCell className="max-w-[220px] truncate font-medium" title={pipeline.name}>
                    <Link
                      to={`/apps/${appId}/workflows/pipelines/${pipeline.id}`}
                      className="hover:underline focus-visible:underline"
                    >
                      {pipeline.name}
                    </Link>
                  </TableCell>
                  <TableCell className="max-w-[240px]">
                    <div className="flex items-center gap-1">
                      <span className="truncate font-mono text-xs" title={pipeline.id}>
                        {pipeline.id}
                      </span>
                      <Button variant="ghost" size="sm" title="Copy ID" onClick={() => void handleCopyId(pipeline.id)}>
                        <Copy className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                  <TableCell className="max-w-[220px] truncate text-sm" title={pipeline.workflow_id || ''}>
                    {workflowNameById.get(pipeline.workflow_id || '') || pipeline.workflow_id || '—'}
                  </TableCell>
                  <TableCell className="text-sm">
                    {pipeline.workflow_version !== undefined ? `v${pipeline.workflow_version}` : '—'}
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap">{formatCreatedAt(pipeline.created_at)}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Button variant="ghost" size="sm" title="Delete" onClick={() => setDeleteItem(pipeline)}>
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
        title="Delete Workflow Pipeline"
        message={`Are you sure you want to delete "${deleteItem?.name}"? This action cannot be undone.`}
        onConfirm={handleDelete}
        onCancel={() => setDeleteItem(null)}
        loading={deleting}
      />

      {appId && (
        <CreateWorkflowPipelineDialog
          isOpen={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          appId={appId}
          onSuccess={handleCreateSuccess}
        />
      )}
    </div>
  );
};

export default WorkflowPipelinesPage;
