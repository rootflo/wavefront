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
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { z } from 'zod';

const defaultYamlContent = `metadata:
  name: content-creation-yaml-workflow
  version: 1.0.0
  description: "Content creation with YAML-defined smart router"

arium:
  agents:
    - name: content_creator
      role: "Content Creator"
      job: "Create initial content drafts on any topic with engaging style."
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.7

    - name: technical_writer
      role: "Technical Writer"
      job: "Specialize in technical documentation, tutorials, and educational content."
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3

    - name: creative_writer
      role: "Creative Writer"
      job: "Specialize in creative writing, storytelling, and marketing content."
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.8

    - name: editor
      role: "Content Editor"
      job: "Review and polish content for clarity, flow, and quality."
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.2

  # Router definitions in YAML
  routers:
    - name: content_router
      type: smart
      routing_options:
        technical_writer: "Handle technical documentation, tutorials, how-to guides, and educational content"
        creative_writer: "Handle creative writing, marketing copy, stories, and engaging content"
        editor: "Move to editing when content is ready for review and polishing"
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3
        context_description: "a content creation workflow that routes based on content type and readiness"
        fallback_strategy: "first"

  workflow:
    start: content_creator
    edges:
      - from: content_creator
        to: [technical_writer, creative_writer, editor]
        router: content_router
      - from: technical_writer
        to: [editor]
      - from: creative_writer
        to: [editor]
    end: [editor]
`;

const createWorkflowSchema = z.object({
  workflow_id: z.string().min(1, 'Workflow ID is required'),
  namespace: z.string().min(1, 'Namespace is required'),
  yaml_content: z.string().min(1, 'YAML content is required'),
});

type CreateWorkflowInput = z.infer<typeof createWorkflowSchema>;

interface CreateWorkflowDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  onSuccess?: () => void;
}

const CreateWorkflowDialog: React.FC<CreateWorkflowDialogProps> = ({ isOpen, onOpenChange, appId, onSuccess }) => {
  const navigate = useNavigate();
  const { notifySuccess, notifyError } = useNotifyStore();

  const [loading, setLoading] = useState(false);

  const form = useForm<CreateWorkflowInput>({
    resolver: zodResolver(createWorkflowSchema),
    defaultValues: {
      workflow_id: '',
      namespace: 'default',
      yaml_content: defaultYamlContent,
    },
  });

  // Reset form when dialog closes
  React.useEffect(() => {
    if (!isOpen) {
      form.reset({
        workflow_id: '',
        namespace: 'default',
        yaml_content: defaultYamlContent,
      });
    }
  }, [isOpen, form]);

  const onSubmit = async (data: CreateWorkflowInput) => {
    setLoading(true);
    try {
      const response = await floConsoleService.workflowService.createWorkflow(
        data.workflow_id.trim(),
        data.yaml_content.trim(),
        data.namespace.trim()
      );

      if (response.data?.meta?.status === 'success' && response.data.data?.data) {
        const createdWorkflowId = response.data.data.data.id;
        notifySuccess('Workflow created successfully');
        onSuccess?.();
        onOpenChange(false);
        navigate(`/apps/${appId}/workflows/${createdWorkflowId}`);
      }
    } catch (error) {
      console.error('Error creating workflow:', error);
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to create workflow');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto lg:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Create New Workflow</DialogTitle>
          <DialogDescription>Create a new AI workflow for voice-intelligence</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="w-full space-y-6">
            <div className="grid w-full grid-cols-2 gap-6">
              <FormField
                control={form.control}
                name="workflow_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Workflow ID</FormLabel>
                    <FormControl>
                      <Input placeholder="my-workflow" {...field} />
                    </FormControl>
                    <FormDescription>Unique identifier for your workflow (lowercase, hyphens allowed)</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="namespace"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Namespace</FormLabel>
                    <FormControl>
                      <Input placeholder="default" {...field} />
                    </FormControl>
                    <FormDescription>Organization namespace for your workflow</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="yaml_content"
              render={({ field }) => (
                <FormItem className="col-span-2 w-full">
                  <FormLabel>Workflow Configuration (YAML)</FormLabel>
                  <FormControl>
                    <div className="w-full rounded-lg border border-gray-300">
                      <CodeMirror
                        value={field.value}
                        onChange={field.onChange}
                        theme="dark"
                        height="400px"
                        width="100%"
                        extensions={[langs.yaml()]}
                        className="w-full"
                      />
                    </div>
                  </FormControl>
                  <FormDescription>
                    Define your workflow's steps, configuration, and processing logic in YAML format
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={loading}>
                Cancel
              </Button>
              <Button type="submit" loading={loading}>
                Create Workflow
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateWorkflowDialog;
