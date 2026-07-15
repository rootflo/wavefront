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
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@app/components/ui/form';
import { Popover, PopoverContent, PopoverTrigger } from '@app/components/ui/popover';
import { cn } from '@app/lib/utils';
import { ToolsDetailsData } from '@app/types/tool';
import { useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import yaml from 'js-yaml';
import { Check, ChevronsUpDown } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

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
  const { notifyError } = useNotifyStore();

  const form = useForm<EditAgentInput>({
    resolver: zodResolver(editAgentSchema),
    defaultValues: {
      yamlContent: initialYamlContent,
      selectedTools: initialSelectedTools,
    },
  });

  useEffect(() => {
    if (isOpen) {
      form.reset({
        yamlContent: initialYamlContent,
        selectedTools: initialSelectedTools,
      });
      setLocalYamlContent(initialYamlContent);
      setLocalSelectedTools(initialSelectedTools);
    }
  }, [initialYamlContent, initialSelectedTools, form, isOpen]);

  // Update YAML when tools change
  useEffect(() => {
    if (!localYamlContent || toolsDetails.length === 0) return;

    const tools = toolsDetails.filter((tool) =>
      localSelectedTools.some((selected) => selected.value === tool.display_name)
    );

    let parsedYaml: { agent?: { tools?: unknown[] } } | null | undefined;
    try {
      parsedYaml = yaml.load(localYamlContent) as { agent?: { tools?: unknown[] } } | null;
    } catch (error) {
      console.error('Failed to parse YAML:', error);
      notifyError('Invalid YAML format. Please fix the YAML syntax before adding tools.');
      return;
    }

    if (parsedYaml && parsedYaml.agent) {
      if (!parsedYaml.agent.tools) {
        parsedYaml.agent.tools = [];
      }

      parsedYaml.agent.tools = tools.map((tool) => {
        const prefilledParams: Record<string, string> | undefined =
          tool.prefilled_values && tool.prefilled_values.length > 0
            ? tool.prefilled_values.reduce(
                (acc: Record<string, string>, obj: { [key: string]: string }) => {
                  return { ...acc, ...obj };
                },
                {} as Record<string, string>
              )
            : undefined;

        return {
          name: tool.name,
          prefilled_params: prefilledParams,
          name_override: tool.name,
          description_override: tool.description,
        };
      });
      setLocalYamlContent(yaml.dump(parsedYaml));
      form.setValue('yamlContent', yaml.dump(parsedYaml));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localSelectedTools, toolsDetails]);

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
      <DialogContent className="max-h-[90vh] w-full overflow-y-auto lg:max-w-5xl">
        <DialogHeader>
          <DialogTitle>Edit Agent{editingVersion !== undefined ? ` (v${editingVersion})` : ''}</DialogTitle>
          <DialogDescription>
            Update the agent configuration and tools. Use &quot;Save&quot; to overwrite this version, or &quot;Save as
            new version&quot; to branch a new, unpromoted version.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit((data) => onSubmit(data, false))} className="w-full space-y-6">
            <div className="grid w-full grid-cols-4 gap-6">
              <FormField
                control={form.control}
                name="yamlContent"
                render={({ field }) => (
                  <FormItem className="col-span-3">
                    <FormLabel>Configuration</FormLabel>
                    <FormControl>
                      <CodeMirror
                        value={localYamlContent}
                        height="400px"
                        extensions={[langs.yaml()]}
                        onChange={(value: string) => {
                          setLocalYamlContent(value);
                          field.onChange(value);
                        }}
                        theme="dark"
                        className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 font-mono text-sm text-black outline-none"
                        placeholder="Enter your agent YAML configuration..."
                      />
                    </FormControl>
                    <FormDescription>
                      Define your agent configuration in YAML format. Configuration varies by agent type.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="selectedTools"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Add Tools</FormLabel>
                    <FormControl>
                      <Popover open={toolsComboboxOpen} onOpenChange={setToolsComboboxOpen}>
                        <PopoverTrigger asChild>
                          <Button
                            type="button"
                            className="w-[240px]"
                            variant="outline"
                            role="combobox"
                            aria-expanded={toolsComboboxOpen}
                          >
                            Select Tools
                            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                          </Button>
                        </PopoverTrigger>
                        <PopoverContent className="w-full p-0" align="start">
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
                                      {tool.display_name}
                                    </CommandItem>
                                  );
                                })}
                              </CommandGroup>
                            </CommandList>
                          </Command>
                        </PopoverContent>
                      </Popover>
                    </FormControl>
                    <FormDescription>Select tools to add to your agent.</FormDescription>
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
