import DeleteConfirmationDialog from '@app/components/DeleteConfirmationDialog';
import { Button } from '@app/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@app/components/ui/command';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Popover, PopoverContent, PopoverTrigger } from '@app/components/ui/popover';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@app/components/ui/tabs';
import { cn } from '@app/lib/utils';
import { ToolsDetailsData } from '@app/types/tool';
import { useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import { popupCodeMirrorExtensions } from '@app/lib/code-mirror';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import { Check, ChevronsUpDown } from 'lucide-react';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { useGetLLMConfigs } from '@app/hooks/data/fetch-hooks';
import { useValidateAgentYaml } from '@app/hooks/data/yaml-validation-hooks';
import { useBeforeUnloadGuard } from '@app/hooks/use-before-unload-guard';
import AgentFormFields from './AgentFormFields';
import {
  EMPTY_AGENT_FORM_VALUES,
  getAgentToolNames,
  isSameYamlDocument,
  setAgentTool,
  type AgentToolOption,
} from './agentYamlMapper';
import { editAgentSchema, type EditAgentInput } from './schemas';
import { useAgentYamlForm } from './useAgentYamlForm';

type SelectedTool = { id: string; value: string };

interface EditAgentDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  yamlContent: string;
  selectedTools: SelectedTool[];
  toolsDetails: ToolsDetailsData[];
  /** Rejects when the save fails; the dialog then stays open with the draft intact. */
  onSave: (yamlContent: string, selectedTools: SelectedTool[], options: { createNewVersion: boolean }) => Promise<void>;
  saving: boolean;
  /** The version currently being edited (for context in the header). */
  editingVersion?: number;
}

const toToolOption = (tool: ToolsDetailsData): AgentToolOption => {
  // Merge all prefilled_values objects ({ datasource_id: "value" }, ...) into a single params object
  const prefilledParams = (tool.prefilled_values ?? []).reduce<Record<string, string>>(
    (acc, entry) => ({ ...acc, ...entry }),
    {}
  );
  return { name: tool.name, description: tool.description, prefilledParams };
};

const EditAgentDialog: React.FC<EditAgentDialogProps> = ({
  isOpen,
  onOpenChange,
  appId,
  yamlContent: initialYamlContent,
  selectedTools: initialSelectedTools,
  toolsDetails,
  onSave,
  saving,
  editingVersion,
}) => {
  const [toolsComboboxOpen, setToolsComboboxOpen] = useState(false);
  const [discardConfirmOpen, setDiscardConfirmOpen] = useState(false);
  const [submitAction, setSubmitAction] = useState<'save' | 'new' | null>(null);
  const { notifyError } = useNotifyStore();
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const validateYaml = useValidateAgentYaml();
  const validating = validateYaml.isPending;

  const { data: llmConfigs = [] } = useGetLLMConfigs(appId);

  const form = useForm<EditAgentInput>({
    resolver: zodResolver(editAgentSchema),
    defaultValues: {
      ...EMPTY_AGENT_FORM_VALUES,
      yamlContent: initialYamlContent,
      selectedTools: initialSelectedTools,
    },
  });

  const { activeTab, handleTabChange, resetFromYaml, handleSubmit } = useAgentYamlForm(form);

  // The dialog loads the agent once per open. A refetch of the agent while it is open must not discard edits.
  const initialRef = useRef({ yamlContent: initialYamlContent, selectedTools: initialSelectedTools });
  useEffect(() => {
    initialRef.current = { yamlContent: initialYamlContent, selectedTools: initialSelectedTools };
  }, [initialYamlContent, initialSelectedTools]);

  useEffect(() => {
    if (!isOpen) return;
    const { yamlContent, selectedTools } = initialRef.current;
    resetFromYaml(yamlContent, { selectedTools });
  }, [isOpen, resetFromYaml]);

  // The YAML is the source of truth for which tools are attached, so edits made on either tab show up here.
  const yamlContent = useWatch({ control: form.control, name: 'yamlContent' });
  const yamlToolNames = useMemo(() => getAgentToolNames(yamlContent), [yamlContent]);

  const toggleTool = (tool: ToolsDetailsData, enabled: boolean) => {
    const result = setAgentTool(form.getValues('yamlContent'), toToolOption(tool), enabled);
    if (!result.ok) {
      notifyError(`Cannot update tools: ${result.error}`);
      return;
    }
    form.setValue('yamlContent', result.yaml, { shouldDirty: true });

    const current = form.getValues('selectedTools') ?? [];
    const others = current.filter((item) => item.value !== tool.display_name);
    form.setValue(
      'selectedTools',
      enabled ? [...others, { id: tool.display_name, value: tool.display_name }] : others,
      {
        shouldDirty: true,
      }
    );
  };

  const hasChanges = (data: EditAgentInput) => {
    const { yamlContent: savedYaml, selectedTools: savedTools } = initialRef.current;
    const toolsUnchanged =
      JSON.stringify((data.selectedTools ?? []).map((tool) => tool.value)) ===
      JSON.stringify(savedTools.map((tool) => tool.value));
    return !(toolsUnchanged && isSameYamlDocument(data.yamlContent, savedYaml));
  };

  const watchedValues = useWatch({ control: form.control });
  const isDirty = isOpen && hasChanges(watchedValues as EditAgentInput);

  useEffect(() => {
    setValidationErrors([]);
  }, [yamlContent]);

  useBeforeUnloadGuard(isDirty);

  // Cancel, Esc and outside clicks all come through here so edits are never dropped silently.
  const requestClose = () => {
    if (saving || validating) return;
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

  useEffect(() => {
    if (!isOpen) setDiscardConfirmOpen(false);
  }, [isOpen]);

  const onSubmit = async (data: EditAgentInput, createNewVersion: boolean) => {
    // Nothing to persist; a new version is the one explicit way to save an unchanged document.
    if (!createNewVersion && !hasChanges(data)) {
      setSubmitAction(null);
      onOpenChange(false);
      return;
    }
    setValidationErrors([]);
    try {
      const validation = await validateYaml.mutateAsync({ yamlContent: data.yamlContent }).catch(() => null);
      if (validation && !validation.valid) {
        setValidationErrors(validation.errors.map((e) => (e.path ? `${e.path}: ${e.message}` : e.message)));
        return;
      }
      await onSave(data.yamlContent, data.selectedTools ?? [], { createNewVersion });
      onOpenChange(false);
    } catch (error) {
      // The request layer already reported the failure; keep the dialog open so the draft is not lost.
      console.error('Error saving agent:', error);
    } finally {
      setSubmitAction(null);
    }
  };

  const toolsField = (
    <FormField
      control={form.control}
      name="selectedTools"
      render={() => (
        <FormItem className="min-w-0">
          <FormLabel className="frost-text">Add Tools</FormLabel>
          <FormControl>
            <Popover open={toolsComboboxOpen} onOpenChange={setToolsComboboxOpen}>
              <PopoverTrigger asChild>
                <Button
                  type="button"
                  className="frost-control w-full min-w-0 justify-between"
                  variant="outline"
                  role="combobox"
                  aria-expanded={toolsComboboxOpen}
                >
                  <span className="truncate">Select Tools</span>
                  <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0" align="start">
                <Command>
                  <CommandInput placeholder="Search tools..." />
                  <CommandList>
                    <CommandEmpty>No tools found.</CommandEmpty>
                    <CommandGroup>
                      {toolsDetails.map((tool) => {
                        const isSelected = yamlToolNames?.has(tool.name) ?? false;
                        return (
                          <CommandItem
                            key={tool.display_name}
                            value={tool.display_name}
                            onSelect={() => toggleTool(tool, !isSelected)}
                          >
                            <Check className={cn('mr-2 h-4 w-4', isSelected ? 'opacity-100' : 'opacity-0')} />
                            <span className="truncate">{tool.display_name}</span>
                          </CommandItem>
                        );
                      })}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
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
            <DialogTitle className="frost-text">
              Edit Agent{editingVersion !== undefined ? ` (v${editingVersion})` : ''}
            </DialogTitle>
            <DialogDescription className="frost-text-muted">
              Update the agent configuration and tools. Use "Save" to overwrite this version, or "Save as new version"
              to branch a new, unpromoted version.
            </DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={handleSubmit((data) => onSubmit(data, false))} className="flex min-h-0 flex-1 flex-col">
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
                    <AgentFormFields appId={appId} llmConfigs={llmConfigs} showAgentName toolsField={toolsField} />
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

                    <div className="mt-4">{toolsField}</div>
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
                    disabled={saving || validating}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    variant="outline"
                    className="frost-control border-frost-border"
                    disabled={saving || validating}
                    loading={(saving || validating) && submitAction === 'save'}
                    onClick={() => setSubmitAction('save')}
                  >
                    Save
                  </Button>
                  <Button
                    type="button"
                    disabled={saving || validating}
                    loading={(saving || validating) && submitAction === 'new'}
                    onClick={() => {
                      setSubmitAction('new');
                      void handleSubmit((data) => onSubmit(data, true))();
                    }}
                  >
                    Save as new version
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
        message="You have unsaved changes to this agent. Closing will discard them."
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        onConfirm={handleDiscard}
        onCancel={() => setDiscardConfirmOpen(false)}
      />
    </>
  );
};

export default EditAgentDialog;
