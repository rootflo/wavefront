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
import { useDashboardStore, useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { z } from 'zod';

const createApiServiceSchema = z.object({
  yamlContent: z.string().min(1, 'YAML configuration is required'),
});

type CreateApiServiceInput = z.infer<typeof createApiServiceSchema>;

const defaultYamlContent = `service:
  id: my-api-service
  base_url: https://api.example.com
  auth:
    id: basic-auth
    version: v1
    type: basic
    username: your-username
    password: your-password
  apis:
    - id: get-users
      version: v1
      path: /users
      backend_path: /api/users
      method: GET
      output_mapper_enabled: false
`;

interface CreateApiServiceDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  onSuccess?: () => void;
}

const CreateApiServiceDialog: React.FC<CreateApiServiceDialogProps> = ({ isOpen, onOpenChange, appId, onSuccess }) => {
  const navigate = useNavigate();
  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();
  const form = useForm<CreateApiServiceInput>({
    resolver: zodResolver(createApiServiceSchema),
    defaultValues: {
      yamlContent: defaultYamlContent.trim(),
    },
  });

  // Reset form when dialog closes
  useEffect(() => {
    if (!isOpen) {
      form.reset({
        yamlContent: defaultYamlContent.trim(),
      });
    }
  }, [isOpen, form]);

  const onSubmit = async (data: CreateApiServiceInput) => {
    try {
      const response = await floConsoleService.apiServiceService.createApiService(data.yamlContent);

      if (response.data?.meta?.status === 'success') {
        notifySuccess('API Service created successfully');

        if (onSuccess) {
          onSuccess();
        }

        onOpenChange(false);

        // Optionally navigate to the created service if we have the ID
        if (response.data?.data?.service_id) {
          navigate(`/apps/${appId}/api-services/${response.data.data.service_id}`);
        }
      }
    } catch (error) {
      console.error('Error creating API service:', error);

      let errorMessage = 'Failed to create API service';

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
          <DialogTitle>Create New API Service</DialogTitle>
          <DialogDescription>Create a new API service for {selectedApp?.app_name}</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <FormField
              control={form.control}
              name="yamlContent"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>API Service Configuration (YAML)</FormLabel>
                  <FormControl>
                    <div className="w-full">
                      <CodeMirror
                        value={field.value}
                        onChange={field.onChange}
                        theme="dark"
                        height="400px"
                        className="w-full"
                        extensions={[langs.yaml()]}
                        placeholder="Enter your API service YAML configuration..."
                      />
                    </div>
                  </FormControl>
                  <FormDescription>Define your API service configuration in YAML format</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={form.formState.isSubmitting}>
                Create API Service
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateApiServiceDialog;
