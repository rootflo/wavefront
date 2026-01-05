import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { ResourceCardSkeleton } from '@app/components/ResourceCard';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import WorkflowPipelineCard from '@app/components/WorkflowPipelineCard';
import { useGetWorkflowPipelines, useGetWorkflows } from '@app/hooks';
import { getWorkflowPipelinesKey } from '@app/hooks/data/query-keys';
import { useNotifyStore } from '@app/store';
import { WorkflowPipelineListItem } from '@app/types/workflow';
import { useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import CreateWorkflowPipelineDialog from './CreateWorkflowPipelineDialog';

const WorkflowPipelinesPage: React.FC = () => {
  const { app: appId } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();
  const [searchTerm, setSearchTerm] = useState('');
  const [workflow, setWorkflow] = useState('');
  const [deleteItem, setDeleteItem] = useState<WorkflowPipelineListItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  // Fetch workflow pipelines and workflows
  const { data: workflowPipelines = [], isLoading: workflowPipelinesLoading } = useGetWorkflowPipelines(appId);
  const { data: workflows = [] } = useGetWorkflows(appId);

  const filteredWorkflowPipelines = workflowPipelines.filter((pipeline) => {
    const matchesSearch =
      pipeline.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      pipeline.id.toLowerCase().includes(searchTerm.toLowerCase());

    // Filter by workflow_id if workflow is selected
    const matchesWorkflow = !workflow || pipeline.workflow_id === workflow;

    return matchesSearch && matchesWorkflow;
  });

  const handleWorkflowChange = (value: string) => {
    setWorkflow(value);
  };

  const handleDeleteClick = (e: React.MouseEvent, pipeline: WorkflowPipelineListItem) => {
    e.stopPropagation();
    setDeleteItem(pipeline);
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
    } catch (error) {
      console.error('Error deleting workflow pipeline:', error);
      notifyError('Failed to delete workflow pipeline');
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteItem(null);
  };

  const handleCreatePipeline = () => {
    setCreateDialogOpen(true);
  };

  const handleCreateSuccess = () => {
    queryClient.invalidateQueries({
      queryKey: getWorkflowPipelinesKey(appId || ''),
    });
    setCreateDialogOpen(false);
  };

  return (
    <div className="h-full w-full overflow-hidden">
      <div className="mb-8 flex items-center justify-end">
        <div className="flex items-center gap-4">
          <Select value={workflow || undefined} onValueChange={(value) => handleWorkflowChange(value || '')}>
            <SelectTrigger className="w-48 cursor-pointer">
              <SelectValue placeholder="All Workflows" />
            </SelectTrigger>
            <SelectContent>
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

          <Button onClick={handleCreatePipeline}>Create Pipeline</Button>
        </div>
      </div>

      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {workflowPipelinesLoading ? (
          <>
            {Array.from({ length: 6 }).map((_, index) => (
              <ResourceCardSkeleton key={index} metadataCount={2} />
            ))}
          </>
        ) : filteredWorkflowPipelines.length === 0 ? (
          <div className="col-span-full mt-10 flex justify-center">
            <EmptyStateCard
              title="No pipelines found"
              description="Get started by creating your first pipeline"
              actionText="Create Pipeline"
              onActionClick={handleCreatePipeline}
            />
          </div>
        ) : (
          <>
            {filteredWorkflowPipelines.map((workflowPipeline) => (
              <WorkflowPipelineCard
                key={workflowPipeline.id}
                pipeline={workflowPipeline}
                onClick={(id) => navigate(`/apps/${appId}/workflows/pipelines/${id}`)}
                onDeleteClick={handleDeleteClick}
              />
            ))}
          </>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={!!deleteItem}
        title="Delete Workflow Pipeline"
        message={`Are you sure you want to delete "${deleteItem?.name}"? This action cannot be undone.`}
        onConfirm={handleDelete}
        onCancel={handleDeleteCancel}
        loading={deleting}
      />

      {/* Create Pipeline Dialog */}
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
