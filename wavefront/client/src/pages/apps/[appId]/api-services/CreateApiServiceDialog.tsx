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
import { useDashboardStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import { popupCodeMirrorExtensions } from '@app/lib/code-mirror';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeEditor from '@app/components/CodeEditor';
import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { z } from 'zod';
import { useCreateApiService } from '@app/hooks';

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
    password: \${secrets.MY_API_PASSWORD}
  apis:
    - id: get-users
      version: v1
      path: /users
      backend_path: /api/users
      method: GET
      description: get users api
      output_mapper_enabled: false
`;

interface CreateApiServiceDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
}

const CreateApiServiceDialog: React.FC<CreateApiServiceDialogProps> = ({ isOpen, onOpenChange, appId }) => {
  const navigate = useNavigate();
  const createApiService = useCreateApiService(appId);
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

  const onSubmit = (data: CreateApiServiceInput) => {
    createApiService.mutate(data.yamlContent, {
      onSuccess: (response) => {
        onOpenChange(false);
        // Open the new service when the response names it
        if (response.data?.data?.service_id) {
          navigate(`/apps/${appId}/api-services/${response.data.data.service_id}`);
        }
      },
    });
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl min-w-0 overflow-y-auto lg:max-w-4xl">
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
                    <div className="w-full min-w-0">
                      <CodeEditor
                        value={field.value}
                        onChange={field.onChange}
                        height="400px"
                        width="100%"
                        maxWidth="100%"
                        className="w-full min-w-0"
                        extensions={[langs.yaml(), ...popupCodeMirrorExtensions]}
                        placeholder="Enter your API service YAML configuration..."
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
              <Button type="submit" loading={createApiService.isPending}>
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
