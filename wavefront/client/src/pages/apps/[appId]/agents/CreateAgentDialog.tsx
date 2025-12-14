import floConsoleService from '@app/api';
import { NamespaceItem } from '@app/api/namespace-service';
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { createAgentSchema, type CreateAgentInput } from './schemas';

const defaultYamlContent = `
apiVersion: flo/alpha-v1
metadata:
  name: translator-agent
  version: 1.0.0
  description: "Agent for translating text with specified tone"

agent:
  name: translator
  role: Professional Translator
  model:
    provider: gemini
    name: gemini-2.5-flash
  settings:
    temperature: 0.7
  job: You are a translator. Use this tone <tone>
`;

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

  const form = useForm<CreateAgentInput>({
    resolver: zodResolver(createAgentSchema),
    defaultValues: {
      agentId: '',
      namespace: 'default',
      yamlContent: defaultYamlContent.trim(),
    },
  });

  // Reset form when dialog closes
  useEffect(() => {
    if (!isOpen) {
      form.reset({
        agentId: '',
        namespace: 'default',
        yamlContent: defaultYamlContent.trim(),
      });
    }
  }, [isOpen, form]);

  const onSubmit = async (data: CreateAgentInput) => {
    try {
      const response = await floConsoleService.agentService.createAgent(data.agentId, data.yamlContent, data.namespace);

      if (response.data?.meta?.status === 'success' && response.data.data?.data) {
        const createdAgentId = response.data.data.data.id;
        notifySuccess('Agent created successfully');

        if (onSuccess) {
          onSuccess();
        }

        onOpenChange(false);

        if (createdAgentId) {
          navigate(`/apps/${appId}/agents/${createdAgentId}`);
        }
      }
    } catch (error) {
      console.error('Error creating agent:', error);

      let errorMessage = 'Failed to create agent';

      if (error && typeof error === 'object' && 'response' in error) {
        const response = (error as any).response;
        if (response?.data?.meta?.error) {
          errorMessage = response.data.meta.error;
        } else if (response?.data?.message) {
          errorMessage = response.data.message;
        }
      }

      notifyError(errorMessage);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] w-full overflow-y-auto lg:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Create New Agent</DialogTitle>
          <DialogDescription>Create a new AI agent for {selectedApp?.app_name}</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <div className="grid grid-cols-2 gap-6">
              <FormField
                control={form.control}
                name="agentId"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Agent ID</FormLabel>
                    <FormControl>
                      <Input placeholder="my-agent" {...field} />
                    </FormControl>
                    <FormDescription>Unique identifier for your agent (lowercase, hyphens allowed)</FormDescription>
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
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select namespace" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {namespaces.length === 0 && <SelectItem value="default">default</SelectItem>}
                        {namespaces.map((ns) => (
                          <SelectItem key={ns.name} value={ns.name}>
                            {ns.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormDescription>Organization namespace for your agent</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="yamlContent"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Agent Configuration (YAML)</FormLabel>
                  <FormControl>
                    <div className="w-full">
                      <CodeMirror
                        value={field.value}
                        onChange={field.onChange}
                        theme="dark"
                        height="400px"
                        className="w-full"
                        extensions={[langs.yaml()]}
                        placeholder="Enter your agent YAML configuration..."
                      />
                    </div>
                  </FormControl>
                  <FormDescription>Define your agent's behavior, model, and variables in YAML format</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={form.formState.isSubmitting}>
                Create Agent
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateAgentDialog;
