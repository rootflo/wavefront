import floConsoleService from '@app/api';
import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { useGetWorkflows, useGetWorkflowVersions } from '@app/hooks/data/fetch-hooks';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { WorkflowPipelineListItem } from '@app/types/workflow';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const CURRENT_VERSION_VALUE = 'current';

const editWorkflowPipelineSchema = z.object({
  workflow_id: z.string().min(1, 'Workflow is required'),
  workflow_version: z.string().optional(),
});

type EditWorkflowPipelineInput = z.infer<typeof editWorkflowPipelineSchema>;

interface EditWorkflowPipelineDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  pipeline: WorkflowPipelineListItem;
  onSuccess?: () => void;
}

const EditWorkflowPipelineDialog: React.FC<EditWorkflowPipelineDialogProps> = ({
  isOpen,
  onOpenChange,
  appId,
  pipeline,
  onSuccess,
}) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const [loading, setLoading] = useState(false);

  const { data: workflows = [], isLoading: workflowsLoading } = useGetWorkflows(appId, undefined);

  const form = useForm<EditWorkflowPipelineInput>({
    resolver: zodResolver(editWorkflowPipelineSchema),
    defaultValues: {
      workflow_id: pipeline.workflow_id || '',
      workflow_version:
        pipeline.workflow_version !== undefined ? String(pipeline.workflow_version) : CURRENT_VERSION_VALUE,
    },
  });

  const selectedWorkflowId = form.watch('workflow_id');
  const { data: workflowVersions = [] } = useGetWorkflowVersions(appId, selectedWorkflowId || undefined);

  // Reset the form to the pipeline's current pin whenever it opens.
  useEffect(() => {
    if (isOpen) {
      form.reset({
        workflow_id: pipeline.workflow_id || '',
        workflow_version:
          pipeline.workflow_version !== undefined ? String(pipeline.workflow_version) : CURRENT_VERSION_VALUE,
      });
    }
  }, [isOpen, pipeline, form]);

  const onSubmit = async (data: EditWorkflowPipelineInput) => {
    setLoading(true);
    try {
      const workflowVersion =
        data.workflow_version && data.workflow_version !== CURRENT_VERSION_VALUE
          ? Number(data.workflow_version)
          : undefined;

      const response = await floConsoleService.workflowService.updateWorkflowPipeline(pipeline.id, {
        workflow_id: data.workflow_id,
        workflow_version: workflowVersion,
      });

      if (response.data?.meta?.status === 'success') {
        notifySuccess('Pipeline updated successfully');
        onSuccess?.();
        onOpenChange(false);
      } else {
        notifyError('Failed to update pipeline');
      }
    } catch (error) {
      console.error('Error updating pipeline:', error);
      notifyError(extractErrorMessage(error) || 'Failed to update pipeline');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Edit Pipeline</DialogTitle>
          <DialogDescription>Repoint this pipeline to a different workflow or version.</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <FormField
              control={form.control}
              name="workflow_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    Workflow <span className="text-red-500">*</span>
                  </FormLabel>
                  <Select
                    onValueChange={(val) => {
                      field.onChange(val);
                      form.setValue('workflow_version', CURRENT_VERSION_VALUE);
                    }}
                    value={field.value}
                    disabled={workflowsLoading}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Choose a workflow" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {workflows.map((workflow) => (
                        <SelectItem key={workflow.id} value={workflow.id}>
                          {workflow.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            {workflowVersions.length > 0 && (
              <FormField
                control={form.control}
                name="workflow_version"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Workflow Version</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value || CURRENT_VERSION_VALUE}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Current version" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value={CURRENT_VERSION_VALUE}>Current version</SelectItem>
                        {[...workflowVersions]
                          .sort((a, b) => a.version - b.version)
                          .map((v) => (
                            <SelectItem key={v.id} value={String(v.version)}>
                              v{v.version}
                              {v.is_current ? ' (current)' : ''}
                            </SelectItem>
                          ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
                Cancel
              </Button>
              <Button type="submit" loading={loading}>
                Save
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default EditWorkflowPipelineDialog;
