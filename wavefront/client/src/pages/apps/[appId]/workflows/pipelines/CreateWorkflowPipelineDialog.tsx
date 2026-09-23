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
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { useGetWorkflows, useGetWorkflowVersions } from '@app/hooks/data/fetch-hooks';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const CURRENT_VERSION_VALUE = 'current';

const createWorkflowPipelineSchema = z.object({
  pipeline_name: z.string().min(1, 'Pipeline name is required'),
  workflow_id: z.string().min(1, 'Workflow is required'),
  workflow_version: z.string().optional(),
});

type CreateWorkflowPipelineInput = z.infer<typeof createWorkflowPipelineSchema>;

interface CreateWorkflowPipelineDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  onSuccess?: () => void;
}

const CreateWorkflowPipelineDialog: React.FC<CreateWorkflowPipelineDialogProps> = ({
  isOpen,
  onOpenChange,
  appId,
  onSuccess,
}) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  const [loading, setLoading] = useState(false);

  // Fetch workflows for the select dropdown
  const { data: workflows = [], isLoading: workflowsLoading } = useGetWorkflows(appId, undefined);

  const form = useForm<CreateWorkflowPipelineInput>({
    resolver: zodResolver(createWorkflowPipelineSchema),
    defaultValues: {
      pipeline_name: '',
      workflow_id: '',
      workflow_version: CURRENT_VERSION_VALUE,
    },
  });

  // Fetch versions for the currently selected workflow (for the version dropdown)
  const selectedWorkflowId = form.watch('workflow_id');
  const { data: workflowVersions = [] } = useGetWorkflowVersions(appId, selectedWorkflowId || undefined);

  // Reset form when dialog closes
  useEffect(() => {
    if (!isOpen) {
      form.reset({
        pipeline_name: '',
        workflow_id: '',
        workflow_version: CURRENT_VERSION_VALUE,
      });
    }
  }, [isOpen, form]);

  const onSubmit = async (data: CreateWorkflowPipelineInput) => {
    setLoading(true);
    try {
      const workflowVersion =
        data.workflow_version && data.workflow_version !== CURRENT_VERSION_VALUE
          ? Number(data.workflow_version)
          : undefined;
      const response = await floConsoleService.workflowService.createWorkflowPipeline(
        data.workflow_id,
        data.pipeline_name.trim(),
        workflowVersion
      );

      if (response.data?.meta?.status === 'success') {
        notifySuccess('Pipeline created successfully');
        onSuccess?.();
        onOpenChange(false);
      } else {
        notifyError('Failed to create pipeline');
      }
    } catch (error) {
      console.error('Error creating pipeline:', error);
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to create pipeline');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl min-w-0 overflow-y-auto lg:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Create Pipeline</DialogTitle>
          <DialogDescription>Create a new workflow pipeline</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <FormField
              control={form.control}
              name="pipeline_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    Pipeline Name <span className="text-red-500">*</span>
                  </FormLabel>
                  <FormControl>
                    <Input placeholder="Enter pipeline name" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="workflow_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    Select Workflow <span className="text-red-500">*</span>
                  </FormLabel>
                  <Select
                    onValueChange={(val) => {
                      field.onChange(val);
                      // Reset version pin when the workflow changes
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
                Create Pipeline
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateWorkflowPipelineDialog;
