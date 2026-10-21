import floConsoleService from '@app/api';
import { Button } from '@app/components/ui/button';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@app/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@app/components/ui/tabs';
import { Form, FormControl, FormField, FormItem, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { popupCodeMirrorExtensions } from '@app/lib/code-mirror';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { z } from 'zod';
import { AGENT_ID_PATTERN, AGENT_ID_PATTERN_MESSAGE } from '@app/constants/workflow-builder';
import LazyWorkflowVisualEditor from './LazyWorkflowVisualEditor';
import { useBeforeUnloadGuard } from '@app/hooks/use-before-unload-guard';
import { useValidateWorkflowYaml } from '@app/hooks/data/yaml-validation-hooks';

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
  workflow_id: z.string().trim().min(1, 'Workflow ID is required').regex(AGENT_ID_PATTERN, AGENT_ID_PATTERN_MESSAGE),
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
  const [discardConfirmOpen, setDiscardConfirmOpen] = useState(false);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const validateYaml = useValidateWorkflowYaml();

  const form = useForm<CreateWorkflowInput>({
    resolver: zodResolver(createWorkflowSchema),
    defaultValues: {
      workflow_id: '',
      namespace: 'default',
      yaml_content: defaultYamlContent,
    },
  });

  const watchedValues = form.watch();
  const isDirty =
    watchedValues.workflow_id.trim() !== '' ||
    watchedValues.namespace !== 'default' ||
    watchedValues.yaml_content !== defaultYamlContent;

  useBeforeUnloadGuard(isOpen && isDirty);

  React.useEffect(() => {
    setValidationErrors([]);
  }, [watchedValues.yaml_content]);

  // Cancel, Esc and overlay clicks all come through here so a half-built workflow is never dropped silently.
  const requestClose = () => {
    if (loading || validateYaml.isPending) return;
    if (isDirty) {
      setDiscardConfirmOpen(true);
      return;
    }
    onOpenChange(false);
  };

  const handleDiscard = () => {
    setDiscardConfirmOpen(false);
    onOpenChange(false);
  };

  // Reset form when dialog closes
  React.useEffect(() => {
    if (!isOpen) {
      setDiscardConfirmOpen(false);
      form.reset({
        workflow_id: '',
        namespace: 'default',
        yaml_content: defaultYamlContent,
      });
    }
  }, [isOpen, form]);

  const onSubmit = async (data: CreateWorkflowInput) => {
    setLoading(true);
    setValidationErrors([]);
    try {
      const validation = await validateYaml.mutateAsync({ yamlContent: data.yaml_content.trim() }).catch(() => null);
      if (validation && !validation.valid) {
        setValidationErrors(validation.errors.map((e) => (e.path ? `${e.path}: ${e.message}` : e.message)));
        return;
      }
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
    <>
      <Dialog open={isOpen} onOpenChange={(open) => (open ? onOpenChange(true) : requestClose())}>
        <DialogContent
          showCloseButton={false}
          // Esc and outside clicks stay available to the canvas, menus and prompts; use Cancel to close.
          onEscapeKeyDown={(event) => event.preventDefault()}
          onInteractOutside={(event) => event.preventDefault()}
          className="bg-background !fixed !inset-0 !top-0 !left-0 z-50 flex !h-screen !max-h-none !w-screen !max-w-none min-w-0 !translate-x-0 !translate-y-0 flex-col !gap-0 overflow-hidden !rounded-none !border-0 !p-0"
        >
          <Form {...form}>
            {validationErrors.length > 0 && (
              <ul className="border-border bg-card text-destructive absolute top-14 right-4 z-40 max-h-48 max-w-md list-disc space-y-0.5 overflow-y-auto rounded-md border py-2 pr-3 pl-7 text-xs shadow-md">
                {validationErrors.map((message, index) => (
                  <li key={index}>{message}</li>
                ))}
              </ul>
            )}
            <div className="flex h-full min-h-0 w-full flex-col">
              <Tabs defaultValue="visual" className="flex h-full min-h-0 w-full flex-col">
                {/* TOP COMMAND BAR */}
                <div className="border-border bg-card/95 z-30 flex h-14 shrink-0 items-center justify-between gap-4 border-b px-4 backdrop-blur-md">
                  {/* Left: Branding & Core Workflow Metadata. Only this part is a <form>, so builder buttons and
                      Enter presses in the studio can never submit it; the Create button targets it via `form`. */}
                  <form
                    id="create-workflow-form"
                    onSubmit={form.handleSubmit(onSubmit)}
                    className="flex items-center gap-3"
                  >
                    <div className="flex items-center gap-2">
                      <div className="bg-primary/10 text-primary flex h-7 w-7 items-center justify-center rounded-lg text-xs font-bold shadow-xs">
                        WF
                      </div>
                      <div>
                        <DialogTitle className="text-foreground text-xs leading-none font-semibold">
                          Create Workflow
                        </DialogTitle>
                        <DialogDescription className="sr-only">Visual workflow builder</DialogDescription>
                        <span className="text-muted-foreground text-[10px]">Studio Builder</span>
                      </div>
                    </div>

                    <div className="bg-border mx-1 h-4 w-[1px]" />

                    <FormField
                      control={form.control}
                      name="workflow_id"
                      render={({ field }) => (
                        <FormItem className="flex items-center gap-1.5 space-y-0">
                          <span className="text-muted-foreground text-[11px] font-medium">ID:</span>
                          <FormControl>
                            <Input
                              placeholder="workflow-id"
                              {...field}
                              className="bg-background h-7 w-44 font-mono text-xs"
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="namespace"
                      render={({ field }) => (
                        <FormItem className="flex items-center gap-1.5 space-y-0">
                          <span className="text-muted-foreground text-[11px] font-medium">Namespace:</span>
                          <FormControl>
                            <Input
                              placeholder="default"
                              {...field}
                              className="bg-background h-7 w-32 font-mono text-xs"
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </form>

                  {/* Center: Tabs Switcher */}
                  <TabsList className="bg-muted/60 h-8 p-0.5">
                    <TabsTrigger value="visual" className="h-7 px-3 text-xs">
                      Visual Builder
                    </TabsTrigger>
                    <TabsTrigger value="yaml" className="h-7 px-3 text-xs">
                      YAML Code
                    </TabsTrigger>
                  </TabsList>

                  {/* Right: Actions */}
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="text-muted-foreground hover:text-foreground h-8 text-xs"
                      onClick={requestClose}
                      disabled={loading}
                    >
                      Cancel
                    </Button>
                    <Button
                      type="submit"
                      form="create-workflow-form"
                      size="sm"
                      className="h-8 text-xs shadow-xs"
                      loading={loading}
                    >
                      Create Workflow
                    </Button>
                  </div>
                </div>

                {/* TABS CONTENT: 100% REMAINING REAL ESTATE */}
                <TabsContent
                  value="visual"
                  forceMount
                  className="m-0 h-[calc(100vh-56px)] min-h-0 w-full flex-1 overflow-hidden outline-none data-[state=inactive]:hidden"
                >
                  <LazyWorkflowVisualEditor
                    yamlContent={watchedValues.yaml_content}
                    onChange={(val) => form.setValue('yaml_content', val, { shouldValidate: true })}
                  />
                </TabsContent>

                <TabsContent value="yaml" className="m-0 h-[calc(100vh-56px)] min-h-0 w-full flex-1 p-4 outline-none">
                  <FormField
                    control={form.control}
                    name="yaml_content"
                    render={({ field }) => (
                      <FormItem className="flex h-full min-w-0 flex-col">
                        <FormControl>
                          <div className="border-border w-full min-w-0 flex-1 overflow-hidden rounded-xl border">
                            <CodeMirror
                              value={field.value}
                              onChange={field.onChange}
                              theme="dark"
                              height="100%"
                              width="100%"
                              maxWidth="100%"
                              extensions={[langs.yaml(), ...popupCodeMirrorExtensions]}
                              className="h-full w-full min-w-0"
                            />
                          </div>
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </TabsContent>
              </Tabs>
            </div>
          </Form>
        </DialogContent>
      </Dialog>

      <DeleteConfirmationDialog
        isOpen={discardConfirmOpen}
        title="Discard unsaved changes?"
        message="This workflow has not been created yet. Closing the editor will discard everything you have built."
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        onConfirm={handleDiscard}
        onCancel={() => setDiscardConfirmOpen(false)}
      />
    </>
  );
};

export default CreateWorkflowDialog;
