import floConsoleService from '@app/api';
import { NamespaceItem } from '@app/api/namespace-service';
import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@app/components/ui/tabs';
import { extractErrorMessage } from '@app/lib/utils';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import { popupCodeMirrorExtensions } from '@app/lib/code-mirror';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import React, { useEffect, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { useGetLLMConfigs } from '@app/hooks/data/fetch-hooks';
import { useValidateAgentYaml } from '@app/hooks/data/yaml-validation-hooks';
import { useBeforeUnloadGuard } from '@app/hooks/use-before-unload-guard';
import AgentFormFields from './AgentFormFields';
import { EMPTY_AGENT_FORM_VALUES, isSameYamlDocument, syncAgentIdentity } from './agentYamlMapper';
import { createAgentSchema, type CreateAgentInput } from './schemas';
import { useAgentYamlForm } from './useAgentYamlForm';

// A skeleton without sample content: agent.name and metadata.name follow the agent name field, and the
// model and system prompt are filled in from the builder.
const defaultYamlContent = `apiVersion: flo/alpha-v1
metadata:
  version: 1.0.0

agent:
  act_as: assistant
  model:
    provider: rootflo
`;

const DEFAULT_NAMESPACE = 'default';

interface CreateAgentDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  onSuccess?: () => void;
  namespaces: NamespaceItem[];
}

const CreateAgentDialog: React.FC<CreateAgentDialogProps> = ({
  isOpen,
  onOpenChange,
  appId,
  onSuccess,
  namespaces,
}) => {
  const navigate = useNavigate();
  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();
  const previousAgentId = useRef('');

  const { data: llmConfigs = [] } = useGetLLMConfigs(appId);

  const form = useForm<CreateAgentInput>({
    resolver: zodResolver(createAgentSchema),
    defaultValues: {
      ...EMPTY_AGENT_FORM_VALUES,
      agentId: '',
      namespace: DEFAULT_NAMESPACE,
      yamlContent: defaultYamlContent,
    },
  });

  const { activeTab, handleTabChange, resetFromYaml, handleSubmit } = useAgentYamlForm(form);

  const [discardConfirmOpen, setDiscardConfirmOpen] = useState(false);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const validateYaml = useValidateAgentYaml();
  const watchedValues = form.watch();
  const isDirty =
    (watchedValues.agentId ?? '').trim() !== '' ||
    watchedValues.namespace !== DEFAULT_NAMESPACE ||
    !isSameYamlDocument(watchedValues.yamlContent ?? '', defaultYamlContent);

  useBeforeUnloadGuard(isOpen && isDirty);

  useEffect(() => {
    setValidationErrors([]);
  }, [watchedValues.yamlContent]);

  // Cancel, Esc and outside clicks all come through here so a half-built agent is never dropped silently.
  const requestClose = () => {
    if (form.formState.isSubmitting) return;
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

  // Every time the dialog opens it starts from the blank skeleton.
  useEffect(() => {
    if (!isOpen) {
      setDiscardConfirmOpen(false);
      return;
    }
    previousAgentId.current = '';
    resetFromYaml(defaultYamlContent, { agentId: '', namespace: DEFAULT_NAMESPACE });
  }, [isOpen, resetFromYaml]);

  // The agent name drives agent.name and metadata.name until the user customises them in the YAML.
  useEffect(() => {
    const subscription = form.watch((values, { name, type }) => {
      if (name !== 'agentId' || type !== 'change') return;
      const agentId = values.agentId ?? '';
      const current = values.yamlContent ?? '';
      const next = syncAgentIdentity(current, agentId, previousAgentId.current);
      previousAgentId.current = agentId;
      if (next !== current) form.setValue('yamlContent', next, { shouldDirty: true });
    });
    return () => subscription.unsubscribe();
  }, [form]);

  const onSubmit = async (data: CreateAgentInput) => {
    setValidationErrors([]);
    try {
      const validation = await validateYaml.mutateAsync({ yamlContent: data.yamlContent }).catch(() => null);
      if (validation && !validation.valid) {
        setValidationErrors(validation.errors.map((e) => (e.path ? `${e.path}: ${e.message}` : e.message)));
        return;
      }
      const response = await floConsoleService.agentService.createAgent(data.agentId, data.yamlContent, data.namespace);

      if (response.data?.meta?.status === 'success' && response.data.data?.data) {
        const createdAgentId = response.data.data.data.id;
        notifySuccess('Agent created successfully');
        if (onSuccess) onSuccess();
        onOpenChange(false);
        if (createdAgentId) navigate(`/apps/${appId}/agents/${createdAgentId}`);
      }
    } catch (error) {
      console.error('Error creating agent:', error);
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to create agent');
    }
  };

  const identityFields = (
    <div className="grid grid-cols-2 gap-6">
      <FormField
        control={form.control}
        name="agentId"
        render={({ field }) => (
          <FormItem>
            <FormLabel className="frost-text">
              Agent Name <span className="text-red-500">*</span>
            </FormLabel>
            <FormControl>
              <Input placeholder="my-agent" className="frost-control" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="namespace"
        render={({ field }) => (
          <FormItem>
            <FormLabel className="frost-text">Namespace</FormLabel>
            <Select onValueChange={field.onChange} value={field.value}>
              <FormControl>
                <SelectTrigger className="frost-control">
                  <SelectValue placeholder="Select namespace" />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                {namespaces.length === 0 && <SelectItem value={DEFAULT_NAMESPACE}>{DEFAULT_NAMESPACE}</SelectItem>}
                {namespaces.map((ns) => (
                  <SelectItem key={ns.name} value={ns.name}>
                    {ns.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FormMessage />
          </FormItem>
        )}
      />
    </div>
  );

  return (
    <>
      <Dialog open={isOpen} onOpenChange={(open) => (open ? onOpenChange(true) : requestClose())}>
        <DialogContent
          onEscapeKeyDown={(event) => {
            if (isDirty) event.preventDefault();
          }}
          onInteractOutside={(event) => {
            if (isDirty) event.preventDefault();
          }}
          className="frost-dialog border-frost-border ring-frost-border flex max-h-[90vh] min-w-0 flex-col gap-0 overflow-hidden p-0 sm:max-w-3xl lg:max-w-4xl"
        >
          <DialogHeader className="border-frost-border border-b p-6 pb-4">
            <DialogTitle className="frost-text">Create New Agent</DialogTitle>
            <DialogDescription className="frost-text-muted">
              Create a new AI agent for {selectedApp?.app_name}
            </DialogDescription>
          </DialogHeader>

          <Form {...form}>
            <form onSubmit={handleSubmit(onSubmit)} className="flex min-h-0 flex-1 flex-col">
              <Tabs value={activeTab} onValueChange={handleTabChange} className="flex min-h-0 flex-1 flex-col">
                <div className="px-6">
                  <TabsList className="border-frost-border flex h-auto w-full justify-start gap-6 rounded-none border-b bg-transparent p-0">
                    <TabsTrigger
                      value="visual"
                      className="data-[state=active]:border-primary frost-text -mb-px rounded-none border-b-2 border-transparent px-0 py-3 data-[state=active]:bg-transparent data-[state=active]:shadow-none [&_[data-tab-underline]]:!hidden"
                    >
                      Agent Builder
                    </TabsTrigger>
                    <TabsTrigger
                      value="yaml"
                      className="data-[state=active]:border-primary frost-text -mb-px rounded-none border-b-2 border-transparent px-0 py-3 data-[state=active]:bg-transparent data-[state=active]:shadow-none [&_[data-tab-underline]]:!hidden"
                    >
                      YAML Code
                    </TabsTrigger>
                  </TabsList>
                </div>

                <div className="min-h-[400px] flex-1 overflow-y-auto p-6">
                  <TabsContent value="visual" className="m-0 space-y-8 outline-none">
                    <AgentFormFields appId={appId} llmConfigs={llmConfigs} identityFields={identityFields} />
                  </TabsContent>

                  <TabsContent value="yaml" className="m-0 h-full outline-none">
                    <FormField
                      control={form.control}
                      name="yamlContent"
                      render={({ field }) => (
                        <FormItem className="flex h-full flex-col">
                          <FormControl>
                            <div className="frost-control border-frost-border w-full min-w-0 flex-1 overflow-hidden rounded-md border">
                              <CodeMirror
                                value={field.value}
                                onChange={field.onChange}
                                theme="dark"
                                height="100%"
                                className="h-full min-h-[400px] w-full"
                                extensions={[langs.yaml(), ...popupCodeMirrorExtensions]}
                                placeholder="Enter your agent YAML configuration..."
                              />
                            </div>
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </TabsContent>
                </div>

                {validationErrors.length > 0 && (
                  <ul className="border-frost-border text-destructive max-h-32 list-disc space-y-0.5 overflow-y-auto border-t px-6 py-3 pl-11 text-xs">
                    {validationErrors.map((message, index) => (
                      <li key={index}>{message}</li>
                    ))}
                  </ul>
                )}
                <DialogFooter className="border-frost-border bg-frost-dialog/50 border-t p-4 backdrop-blur-md">
                  <Button
                    type="button"
                    variant="outline"
                    className="frost-control border-frost-border"
                    onClick={requestClose}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" loading={form.formState.isSubmitting}>
                    Create Agent
                  </Button>
                </DialogFooter>
              </Tabs>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      <DeleteConfirmationDialog
        isOpen={discardConfirmOpen}
        title="Discard unsaved changes?"
        message="This agent has not been created yet. Closing will discard everything you have entered."
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        onConfirm={handleDiscard}
        onCancel={() => setDiscardConfirmOpen(false)}
      />
    </>
  );
};

export default CreateAgentDialog;
