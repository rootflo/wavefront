import floConsoleService from '@app/api';
import { Button } from '@app/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@app/components/ui/dialog';
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
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { createDatasourceSchema, type CreateDatasourceInput } from './schemas';

const DATASOURCE_TYPES = [
  { value: 'gcp_bigquery', label: 'Google BigQuery' },
  { value: 'aws_redshift', label: 'AWS Redshift' },
];

const SAMPLE_CONFIGS = {
  gcp_bigquery: {
    project_id: 'your-project-id',
    dataset_id: 'your-dataset-id',
    location: 'US',
    credentials_path: '/path/to/service-account.json',
    credentials_json: '{ ... service account JSON ... }',
  },
  aws_redshift: {
    host: 'your-cluster.region.redshift.amazonaws.com',
    port: 5439,
    database: 'your-database',
    user: 'your-username',
    password: 'your-password',
  },
};

interface CreateDatasourceDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  onSuccess?: () => void;
}

const CreateDatasourceDialog: React.FC<CreateDatasourceDialogProps> = ({ isOpen, onOpenChange, appId, onSuccess }) => {
  const navigate = useNavigate();
  const { notifySuccess, notifyError } = useNotifyStore();

  const form = useForm<CreateDatasourceInput>({
    resolver: zodResolver(createDatasourceSchema),
    defaultValues: {
      name: '',
      type: 'gcp_bigquery',
      description: '',
      connectionConfig: JSON.stringify(SAMPLE_CONFIGS.gcp_bigquery, null, 2),
    },
  });

  const datasourceType = form.watch('type');

  // Update connection config when type changes
  useEffect(() => {
    if (datasourceType) {
      form.setValue(
        'connectionConfig',
        JSON.stringify(SAMPLE_CONFIGS[datasourceType as keyof typeof SAMPLE_CONFIGS], null, 2)
      );
    }
  }, [datasourceType, form]);

  // Reset form when dialog closes
  useEffect(() => {
    if (!isOpen) {
      form.reset();
    }
  }, [isOpen, form]);

  const onSubmit = async (data: CreateDatasourceInput) => {
    if (!appId) {
      notifyError('Datasource service not available');
      return;
    }

    let parsedConfig;
    try {
      parsedConfig = JSON.parse(data.connectionConfig);
    } catch {
      notifyError('Invalid JSON in connection configuration');
      return;
    }

    try {
      const response = await floConsoleService.datasourcesService.createDatasource(
        data.name,
        data.type,
        parsedConfig,
        data.description?.trim() || undefined
      );

      const responseData = response.data?.data as { datasource_id?: string } | undefined;
      notifySuccess('Datasource created successfully');

      if (onSuccess) {
        onSuccess();
      }

      onOpenChange(false);

      if (responseData?.datasource_id) {
        navigate(`/apps/${appId}/datasources/${responseData.datasource_id}`);
      }
    } catch (error) {
      console.error('Error creating datasource:', error);
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to create datasource');
    }
  };

  if (!appId) {
    return null;
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto lg:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Create New Datasource</DialogTitle>
          {/* <DialogDescription>Create a new data connection for {currentApp.app_name}</DialogDescription> */}
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <div className="grid grid-cols-2 gap-6">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Datasource Name</FormLabel>
                    <FormControl>
                      <Input placeholder="My Data Connection" {...field} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Datasource Type</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select datasource type" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {DATASOURCE_TYPES.map((type) => (
                          <SelectItem key={type.value} value={type.value}>
                            {type.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    Description <span className="text-gray-400">(Optional)</span>
                  </FormLabel>
                  <FormControl>
                    <Input placeholder="Brief description of this datasource" {...field} />
                  </FormControl>
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="connectionConfig"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Connection Configuration (JSON)</FormLabel>
                  <FormControl>
                    <div className="w-full">
                      <CodeMirror
                        value={field.value}
                        onChange={field.onChange}
                        theme="dark"
                        height="300px"
                        className="w-full"
                        extensions={[langs.json()]}
                        placeholder="Enter your connection configuration in JSON format..."
                      />
                    </div>
                  </FormControl>
                  <FormDescription>
                    Define your connection parameters in JSON format. Configuration varies by datasource type.
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
                Create Datasource
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateDatasourceDialog;
