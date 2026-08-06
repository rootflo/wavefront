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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { useGetNamespaces } from '@app/hooks';
import { useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';

const createConfigurationSchema = z.object({
  namespace: z.string().min(1, 'Namespace is required'),
  key: z.string().trim().min(1, 'Key is required'),
  description: z.string().optional(),
  // Validated here rather than server-side so the editor can point at the
  // problem while the document is still in front of the user.
  value: z
    .string()
    .min(1, 'Value is required')
    .refine((raw) => {
      try {
        JSON.parse(raw);
        return true;
      } catch {
        return false;
      }
    }, 'Value must be valid JSON'),
});

type CreateConfigurationInput = z.infer<typeof createConfigurationSchema>;

const defaultValue = `{
  "enabled": true,
  "limits": {
    "daily": 5000
  }
}`;

interface CreateConfigurationDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  onSuccess?: () => void;
}

const CreateConfigurationDialog: React.FC<CreateConfigurationDialogProps> = ({
  isOpen,
  onOpenChange,
  appId,
  onSuccess,
}) => {
  const { notifySuccess, notifyError } = useNotifyStore();
  // A dropdown rather than a text field: the server rejects a namespace that
  // does not exist, so offering only real ones turns a 400 into an impossible
  // choice.
  const { data: namespaces = [] } = useGetNamespaces(appId);

  const form = useForm<CreateConfigurationInput>({
    resolver: zodResolver(createConfigurationSchema),
    defaultValues: {
      namespace: '',
      key: '',
      description: '',
      value: defaultValue,
    },
  });

  useEffect(() => {
    if (!isOpen) {
      form.reset({
        namespace: '',
        key: '',
        description: '',
        value: defaultValue,
      });
    }
  }, [isOpen, form]);

  const onSubmit = async (data: CreateConfigurationInput) => {
    try {
      const response = await floConsoleService.configurationService.createConfiguration({
        namespace: data.namespace,
        key: data.key.trim(),
        value: JSON.parse(data.value),
        description: data.description?.trim() || undefined,
      });

      if (response.data) {
        notifySuccess('Configuration created successfully');
        onSuccess?.();
        onOpenChange(false);
      } else {
        notifyError('Failed to create configuration');
      }
    } catch (error) {
      console.error('Error creating configuration:', error);
    }
  };

  if (!appId) {
    return null;
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto lg:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Create New Configuration</DialogTitle>
          <DialogDescription>Static reference data workflows read at runtime</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <div className="grid grid-cols-3 gap-6">
              <FormField
                control={form.control}
                name="namespace"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Namespace<span className="text-red-500">*</span>
                    </FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select namespace" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {namespaces.map((namespace) => (
                          <SelectItem key={namespace.name} value={namespace.name}>
                            {namespace.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Key<span className="text-red-500">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="e.g. thresholds" {...field} />
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
                      <Input placeholder="Optional" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="value"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    Value<span className="text-red-500">*</span>
                  </FormLabel>
                  <FormControl>
                    <div className="w-full">
                      <CodeMirror
                        value={field.value}
                        onChange={field.onChange}
                        theme="dark"
                        height="400px"
                        className="w-full"
                        extensions={[langs.json()]}
                        placeholder="Enter the configuration document as JSON..."
                      />
                    </div>
                  </FormControl>
                  <FormDescription>
                    Any JSON document. A workflow reads it with a <code>fetch_configuration</code> node and passes it to
                    a function for calculations.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={form.formState.isSubmitting}>
                Create Configuration
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateConfigurationDialog;
