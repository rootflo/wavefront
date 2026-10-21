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
import { cn } from '@app/lib/utils';
import { ToolsDetailsData } from '@app/types/tool';
import { useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import { popupCodeMirrorExtensions } from '@app/lib/code-mirror';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import yaml from 'js-yaml';
import { Check, ChevronsUpDown } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { buildYamlToolsFromSelection, selectedToolsEqual, selectedToolsFromYaml } from './agent-tools';

const editAgentSchema = z.object({
  yamlContent: z.string().min(1, 'YAML content is required'),
  selectedTools: z.array(z.object({ id: z.string(), value: z.string() })).optional(),
});

type EditAgentInput = z.infer<typeof editAgentSchema>;

interface EditAgentDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  yamlContent: string;
  selectedTools: { id: string; value: string }[];
  toolsDetails: ToolsDetailsData[];
  onSave: (
    yamlContent: string,
    selectedTools: { id: string; value: string }[],
    options: { createNewVersion: boolean }
  ) => Promise<void>;
  saving: boolean;
  /** The version currently being edited (for context in the header). */
  editingVersion?: number;
}

const EditAgentDialog: React.FC<EditAgentDialogProps> = ({
  isOpen,
  onOpenChange,
  yamlContent: initialYamlContent,
  selectedTools: initialSelectedTools,
  toolsDetails,
  onSave,
  saving,
  editingVersion,
}) => {
  const [localYamlContent, setLocalYamlContent] = useState(initialYamlContent);
  const [localSelectedTools, setLocalSelectedTools] = useState(initialSelectedTools);
  const [toolsComboboxOpen, setToolsComboboxOpen] = useState(false);
  const [submitAction, setSubmitAction] = useState<'save' | 'new' | null>(null);
  const skipNextToolsYamlSyncRef = useRef(false);
  const { notifyError } = useNotifyStore();

  const form = useForm<EditAgentInput>({
    resolver: zodResolver(editAgentSchema),
    defaultValues: {
      yamlContent: initialYamlContent,
      selectedTools: initialSelectedTools,
    },
  });

  useEffect(() => {
    if (!isOpen) return;

    let selected = initialSelectedTools;
    // Parent may still be hydrating; recover selection from YAML so opening
    // the dialog never clears agent.tools via the sync effect below.
    if (selected.length === 0 && initialYamlContent && toolsDetails.length > 0) {
      selected = selectedToolsFromYaml(initialYamlContent, toolsDetails);
    }

    skipNextToolsYamlSyncRef.current = true;
    form.reset({
      yamlContent: initialYamlContent,
      selectedTools: selected,
    });
    setLocalYamlContent(initialYamlContent);
    setLocalSelectedTools(selected);
  }, [initialYamlContent, initialSelectedTools, form, isOpen, toolsDetails]);

  // Update YAML when tools change (skip the reset/hydration pass).
  useEffect(() => {
    if (!isOpen || !localYamlContent || toolsDetails.length === 0) return;
    if (skipNextToolsYamlSyncRef.current) {
      skipNextToolsYamlSyncRef.current = false;
      return;
    }

    let parsedYaml: { agent?: { tools?: unknown[] } } | null | undefined;
    try {
      parsedYaml = yaml.load(localYamlContent) as { agent?: { tools?: unknown[] } } | null;
    } catch (error) {
      console.error('Failed to parse YAML:', error);
      notifyError('Invalid YAML format. Please fix the YAML syntax before adding tools.');
      return;
    }

    if (!parsedYaml?.agent) return;

    const existingTools = parsedYaml.agent.tools || [];
    const newTools = buildYamlToolsFromSelection(localSelectedTools, toolsDetails);
    const toolsChanged =
      existingTools.length !== newTools.length ||
      existingTools.some((existingTool: unknown, index: number) => {
        const newTool = newTools[index];
        if (!newTool) return true;
        const existing = existingTool as {
          name?: string;
          prefilled_params?: Record<string, string>;
        };
        return (
          existing.name !== newTool.name ||
          JSON.stringify(existing.prefilled_params || {}) !== JSON.stringify(newTool.prefilled_params || {})
        );
      });

    if (!toolsChanged) return;

    parsedYaml.agent.tools = newTools;
    const dumped = yaml.dump(parsedYaml);
    setLocalYamlContent(dumped);
    form.setValue('yamlContent', dumped);
    // Keep form selectedTools in sync for submit.
    if (!selectedToolsEqual(form.getValues('selectedTools') || [], localSelectedTools)) {
      form.setValue('selectedTools', localSelectedTools);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localSelectedTools, toolsDetails, isOpen]);

  // createNewVersion is passed in directly by the clicked button (not read from
  // submitAction state), so react-hook-form's async submit can't act on a stale
  // value. submitAction is kept only to drive the per-button loading spinner.
  const onSubmit = async (data: EditAgentInput, createNewVersion: boolean) => {
    await onSave(data.yamlContent, data.selectedTools || [], { createNewVersion });
    setSubmitAction(null);
    onOpenChange(false);
  };

  const handleClose = () => {
    onOpenChange(false);
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl min-w-0 overflow-y-auto lg:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Edit Agent{editingVersion !== undefined ? ` (v${editingVersion})` : ''}</DialogTitle>
          <DialogDescription>
            Update the agent configuration and tools. Use &quot;Save&quot; to overwrite this version, or &quot;Save as
            new version&quot; to branch a new, unpromoted version.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit((data) => onSubmit(data, false))} className="w-full space-y-6">
            <div className="grid w-full min-w-0 grid-cols-4 gap-6 overflow-x-hidden">
              <FormField
                control={form.control}
                name="yamlContent"
                render={({ field }) => (
                  <FormItem className="col-span-3 min-w-0">
                    <FormLabel>Configuration</FormLabel>
                    <FormControl>
                      <CodeMirror
                        value={localYamlContent}
                        height="400px"
                        width="100%"
                        maxWidth="100%"
                        extensions={[langs.yaml(), ...popupCodeMirrorExtensions]}
                        onChange={(value: string) => {
                          setLocalYamlContent(value);
                          field.onChange(value);
                        }}
                        theme="dark"
                        className="frost-control ring-frost-border w-full min-w-0 rounded-lg border px-3 py-2 font-mono text-sm ring-1 outline-none"
                        placeholder="Enter your agent YAML configuration..."
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="selectedTools"
                render={({ field }) => (
                  <FormItem className="min-w-0">
                    <FormLabel>Add Tools</FormLabel>
                    <FormControl>
                      <Popover open={toolsComboboxOpen} onOpenChange={setToolsComboboxOpen}>
                        <PopoverTrigger asChild>
                          <Button
                            type="button"
                            className="w-full min-w-0 justify-between"
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
                                  const isSelected = localSelectedTools.some(
                                    (selected) => selected.value === tool.display_name
                                  );
                                  return (
                                    <CommandItem
                                      key={tool.display_name}
                                      value={tool.display_name}
                                      onSelect={() => {
                                        let newSelectedTools;
                                        if (isSelected) {
                                          newSelectedTools = localSelectedTools.filter(
                                            (item) => item.value !== tool.display_name
                                          );
                                        } else {
                                          newSelectedTools = [
                                            ...localSelectedTools,
                                            { id: tool.display_name, value: tool.display_name },
                                          ];
                                        }
                                        setLocalSelectedTools(newSelectedTools);
                                        field.onChange(newSelectedTools);
                                      }}
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
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={handleClose} disabled={saving}>
                Cancel
              </Button>
              <Button
                type="submit"
                variant="outline"
                disabled={saving}
                loading={saving && submitAction === 'save'}
                onClick={() => setSubmitAction('save')}
              >
                Save
              </Button>
              <Button
                type="button"
                disabled={saving}
                loading={saving && submitAction === 'new'}
                onClick={() => {
                  setSubmitAction('new');
                  form.handleSubmit((data) => onSubmit(data, true))();
                }}
              >
                Save as new version
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default EditAgentDialog;
