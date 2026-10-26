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
import { useDashboardStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import { popupCodeMirrorExtensions } from '@app/lib/code-mirror';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeEditor from '@app/components/CodeEditor';
import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { useCreateMessageProcessor } from '@app/hooks';

const createMessageProcessorSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
  yamlContent: z.string().min(1, 'YAML configuration is required'),
});

type CreateMessageProcessorInput = z.infer<typeof createMessageProcessorSchema>;

const defaultYamlContent = `type: javascript
description: double the number
function:
  code: |
    export default function(input) {

      return {
        result: Number(input.number) * 2 };
    }

input_schema:
  required:
    - number
  properties:
    number:
      type: number
      description: The number to process
`;

interface CreateMessageProcessorDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
}

const CreateMessageProcessorDialog: React.FC<CreateMessageProcessorDialogProps> = ({ isOpen, onOpenChange, appId }) => {
  const { selectedApp } = useDashboardStore();
  const createMessageProcessor = useCreateMessageProcessor(appId);
  const form = useForm<CreateMessageProcessorInput>({
    resolver: zodResolver(createMessageProcessorSchema),
    defaultValues: {
      name: '',
      description: '',
      yamlContent: defaultYamlContent.trim(),
    },
  });

  // Reset form when dialog closes
  useEffect(() => {
    if (!isOpen) {
      form.reset({
        name: '',
        description: '',
        yamlContent: defaultYamlContent.trim(),
      });
    }
  }, [isOpen, form]);

  const onSubmit = (data: CreateMessageProcessorInput) => {
    createMessageProcessor.mutate(
      {
        name: data.name.trim(),
        yaml_content: data.yamlContent.trim(),
        description: data.description?.trim() || undefined,
      },
      { onSuccess: () => onOpenChange(false) }
    );
  };

  if (!appId) {
    return null;
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl min-w-0 overflow-y-auto lg:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Create New Message Processor</DialogTitle>
          <DialogDescription>Create a new message processor for {selectedApp?.app_name}</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Name<span className="text-red-500">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="Enter processor name" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Description</FormLabel>
                    <FormControl>
                      <Input placeholder="Enter processor description (optional)" {...field} />
                    </FormControl>
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
                  <FormLabel>
                    YAML Configuration<span className="text-red-500">*</span>
                  </FormLabel>
                  <FormControl>
                    <div className="w-full min-w-0">
                      <CodeEditor
                        value={field.value}
                        onChange={field.onChange}
                        height="400px"
                        width="100%"
                        maxWidth="100%"
                        className="w-full min-w-0"
                        extensions={[langs.yaml(), ...popupCodeMirrorExtensions]}
                        placeholder="Enter your message processor YAML configuration..."
                      />
                    </div>
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={createMessageProcessor.isPending}>
                Create Processor
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateMessageProcessorDialog;
