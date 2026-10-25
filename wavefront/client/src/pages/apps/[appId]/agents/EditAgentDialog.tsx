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
import CodeEditor from '@app/components/CodeEditor';
import { Check, ChevronsUpDown, X } from 'lucide-react';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { useGetLLMConfigs } from '@app/hooks/data/fetch-hooks';
import { useValidateAgentYaml } from '@app/hooks/data/yaml-validation-hooks';
import { useBeforeUnloadGuard } from '@app/hooks/use-before-unload-guard';
import AgentFormFields, { type AgentFormSection } from './AgentFormFields';
import { SECTION_OF_FIELD } from './agentFormSections';
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
  // Each form section is its own tab, followed by the YAML. All three sections count as the hook's "visual" tab.
  const [section, setSection] = useState<AgentFormSection | 'tools'>('identity');
  const currentTab = activeTab === 'yaml' ? 'yaml' : section;

  const handleSectionChange = (value: string) => {
    if (value === 'yaml') {
      handleTabChange('yaml');
      return;
    }
    setSection(value as AgentFormSection | 'tools');
    // Coming back from the YAML re-derives the fields from it first, and stays there if it cannot be read.
    if (activeTab === 'yaml') handleTabChange('visual');
  };

  // A failed save reports the first invalid field; open the tab that has it so its message is visible.
  const firstErrorField = Object.keys(form.formState.errors)[0];
  useEffect(() => {
    if (!firstErrorField || firstErrorField === 'yamlContent') return;
    setSection(firstErrorField === 'selectedTools' ? 'tools' : (SECTION_OF_FIELD[firstErrorField] ?? 'identity'));
  }, [firstErrorField, form.formState.submitCount]);

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

  const selectedToolDetails = toolsDetails.filter((tool) => yamlToolNames?.has(tool.name));

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
          className="flex h-[760px] max-h-[calc(100dvh-2rem)] min-w-0 flex-col overflow-hidden sm:max-w-3xl lg:max-w-4xl"
        >
          <DialogHeader>
            <DialogTitle>Edit Agent{editingVersion !== undefined ? ` (v${editingVersion})` : ''}</DialogTitle>
            <DialogDescription>
              Update the agent configuration and tools. Use "Save" to overwrite this version, or "Save as new version"
              to branch a new, unpromoted version.
            </DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form
              onSubmit={handleSubmit((data) => onSubmit(data, false))}
              className="flex min-h-0 flex-1 flex-col gap-4"
            >
              <Tabs value={currentTab} onValueChange={handleSectionChange} className="flex min-h-0 flex-1 flex-col">
                <div>
                  <TabsList className="border-frost-border flex h-auto w-full max-w-none justify-start gap-6 overflow-visible rounded-none border-0 border-b bg-transparent! p-0 shadow-none! ring-0 sm:justify-start">
                    <TabsTrigger
                      value="identity"
                      className="frost-text data-[state=active]:border-brand -mb-px h-auto flex-none rounded-none border-0 border-b-2 border-transparent bg-transparent! px-0 py-3 shadow-none! data-[state=active]:bg-transparent! data-[state=active]:shadow-none! [&_[data-tab-underline]]:hidden!"
                    >
                      Identity
                    </TabsTrigger>
                    <TabsTrigger
                      value="model"
                      className="frost-text data-[state=active]:border-brand -mb-px h-auto flex-none rounded-none border-0 border-b-2 border-transparent bg-transparent! px-0 py-3 shadow-none! data-[state=active]:bg-transparent! data-[state=active]:shadow-none! [&_[data-tab-underline]]:hidden!"
                    >
                      Model
                    </TabsTrigger>
                    <TabsTrigger
                      value="advanced"
                      className="frost-text data-[state=active]:border-brand -mb-px h-auto flex-none rounded-none border-0 border-b-2 border-transparent bg-transparent! px-0 py-3 shadow-none! data-[state=active]:bg-transparent! data-[state=active]:shadow-none! [&_[data-tab-underline]]:hidden!"
                    >
                      Advanced
                    </TabsTrigger>
                    <TabsTrigger
                      value="tools"
                      className="frost-text data-[state=active]:border-brand -mb-px h-auto flex-none rounded-none border-0 border-b-2 border-transparent bg-transparent! px-0 py-3 shadow-none! data-[state=active]:bg-transparent! data-[state=active]:shadow-none! [&_[data-tab-underline]]:hidden!"
                    >
                      Tools
                    </TabsTrigger>
                    <TabsTrigger
                      value="yaml"
                      className="frost-text data-[state=active]:border-brand -mb-px h-auto flex-none rounded-none border-0 border-b-2 border-transparent bg-transparent! px-0 py-3 shadow-none! data-[state=active]:bg-transparent! data-[state=active]:shadow-none! [&_[data-tab-underline]]:hidden!"
                    >
                      YAML Code
                    </TabsTrigger>
                  </TabsList>
                </div>

                <div className="flex min-h-0 flex-1 flex-col overflow-y-auto pt-5 pb-2">
                  {(['identity', 'model', 'advanced'] as const).map((id) => (
                    <TabsContent key={id} value={id} className="m-0 space-y-8 outline-none">
                      <AgentFormFields appId={appId} llmConfigs={llmConfigs} showAgentName section={id} />
                    </TabsContent>
                  ))}

                  <TabsContent value="tools" className="m-0 space-y-4 outline-none">
                    {toolsField}
                    {selectedToolDetails.length > 0 ? (
                      <ul className="space-y-2">
                        {selectedToolDetails.map((tool) => (
                          <li
                            key={tool.name}
                            className="border-frost-border flex items-start justify-between gap-3 rounded-xl border p-3"
                          >
                            <div className="min-w-0">
                              <p className="frost-text text-sm font-semibold">{tool.display_name}</p>
                              <p className="frost-text-muted mt-0.5 text-[13px] leading-snug">
                                {tool.description || 'No description'}
                              </p>
                            </div>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              aria-label={`Remove ${tool.display_name}`}
                              className="frost-text-muted -mt-1 -mr-1 size-8 shrink-0"
                              onClick={() => toggleTool(tool, false)}
                            >
                              <X className="size-4" />
                            </Button>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="frost-text-muted text-sm">No tools selected yet. Use the list above to add some.</p>
                    )}
                  </TabsContent>

                  <TabsContent
                    value="yaml"
                    className="m-0 min-h-0 flex-1 outline-none data-[state=active]:flex data-[state=active]:flex-col"
                  >
                    <FormField
                      control={form.control}
                      name="yamlContent"
                      render={({ field }) => (
                        <FormItem className="flex min-h-0 flex-1 flex-col">
                          <FormControl>
                            <div className="frost-control border-frost-border flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden rounded-md border">
                              <CodeEditor
                                value={field.value}
                                onChange={field.onChange}
                                height="100%"
                                className="min-h-0 w-full flex-1 [&_.cm-editor]:h-full [&_.cm-scroller]:overflow-auto"
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
                  <ul className="text-destructive max-h-32 list-disc space-y-0.5 overflow-y-auto pl-5 text-xs">
                    {validationErrors.map((message, index) => (
                      <li key={index}>{message}</li>
                    ))}
                  </ul>
                )}
                <DialogFooter>
                  <Button type="button" variant="outline" onClick={requestClose} disabled={saving || validating}>
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    variant="outline"
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
