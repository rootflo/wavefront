import floConsoleService from '@app/api';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { EmptyStateCard } from '@app/components/EmptyCard';
import { ResourceCardSkeleton } from '@app/components/ResourceCard';
import { Button } from '@app/components/ui/button';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import WorkflowCard from '@app/components/WorkflowCard';
import { useGetNamespaces, useGetWorkflows } from '@app/hooks';
import { getWorkflowsKey } from '@app/hooks/data/query-keys';
import { useNotifyStore } from '@app/store';
import { WorkflowListItem } from '@app/types/workflow';
import { useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import CreateWorkflowDialog from './CreateWorkflowDialog';

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

  // Fetch workflows and namespaces
  const { data: workflows = [], isLoading: loading } = useGetWorkflows(appId, namespace || undefined);
  const { data: namespaces = [] } = useGetNamespaces(appId);

  const filteredWorkflows = workflows.filter(
    (workflow) =>
      workflow.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      workflow.id.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleNamespaceChange = (value: string) => {
    setNamespace(value);
  };

  const handleDeleteClick = (e: React.MouseEvent, workflow: WorkflowListItem) => {
    e.stopPropagation();
    setDeleteItem(workflow);
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
    } catch (error) {
      console.error('Error deleting workflow:', error);
      notifyError('Failed to delete workflow');
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteItem(null);
  };

  const handleCreateWorkflow = () => {
    setCreateDialogOpen(true);
  };

  const handleCreateSuccess = () => {
    queryClient.invalidateQueries({
      queryKey: getWorkflowsKey(appId || '', namespace || undefined),
    });
    setCreateDialogOpen(false);
  };

  return (
    <div className="h-full w-full overflow-hidden">
      <div className="mb-8 flex items-center justify-end">
        <div className="flex items-center gap-4">
          <Select value={namespace || undefined} onValueChange={(value) => handleNamespaceChange(value || '')}>
            <SelectTrigger className="w-48 cursor-pointer">
              <SelectValue placeholder="All Namespaces" />
            </SelectTrigger>
            <SelectContent>
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

          <Button onClick={handleCreateWorkflow}>Create Workflow</Button>
        </div>
      </div>

      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {loading ? (
          <>
            {Array.from({ length: 6 }).map((_, index) => (
              <ResourceCardSkeleton key={index} metadataCount={2} />
            ))}
          </>
        ) : filteredWorkflows.length === 0 ? (
          <div className="col-span-full mt-10 flex justify-center">
            <EmptyStateCard
              title="No workflows found"
              description="Get started by creating your first workflow"
              actionText="Create Workflow"
              onActionClick={handleCreateWorkflow}
            />
          </div>
        ) : (
          <>
            {filteredWorkflows.map((workflow) => (
              <WorkflowCard
                key={workflow.id}
                workflow={workflow}
                onClick={(id) => navigate(`/apps/${appId}/workflows/${id}`)}
                onDeleteClick={handleDeleteClick}
              />
            ))}
          </>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <DeleteConfirmationDialog
        isOpen={!!deleteItem}
        title="Delete Workflow"
        message={`Are you sure you want to delete "${deleteItem?.name}"? This action cannot be undone.`}
        onConfirm={handleDelete}
        onCancel={handleDeleteCancel}
        loading={deleting}
      />

      {/* Create Workflow Dialog */}
      {appId && (
        <CreateWorkflowDialog
          isOpen={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          appId={appId}
          onSuccess={handleCreateSuccess}
        />
      )}
    </div>
  );
};

export default WorkflowManagement;
