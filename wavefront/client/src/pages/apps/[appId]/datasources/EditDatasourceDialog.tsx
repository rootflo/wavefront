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
import { Datasource } from '@app/types/datasource';
import { zodResolver } from '@hookform/resolvers/zod';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { createDatasourceSchema, type CreateDatasourceInput } from './schemas';

const DATASOURCE_TYPES = [
  { value: 'gcp_bigquery', label: 'Google BigQuery' },
  { value: 'aws_redshift', label: 'AWS Redshift' },
];

interface EditDatasourceDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  datasource: Datasource;
  onSuccess?: () => void;
}

const EditDatasourceDialog: React.FC<EditDatasourceDialogProps> = ({
  isOpen,
  onOpenChange,
  appId,
  datasource,
  onSuccess,
}) => {
  const { notifySuccess, notifyError } = useNotifyStore();

  const form = useForm<CreateDatasourceInput>({
    resolver: zodResolver(createDatasourceSchema),
    defaultValues: {
      name: '',
      type: 'gcp_bigquery',
      description: '',
      connectionConfig: '',
    },
  });

  // Populate form when datasource data is available
  useEffect(() => {
    if (datasource && isOpen) {
      form.reset({
        name: datasource.name || '',
        type: (datasource.type as 'gcp_bigquery' | 'aws_redshift') || 'gcp_bigquery',
        description: datasource.description || '',
        connectionConfig: JSON.stringify(datasource.config || {}, null, 2),
      });
    }
  }, [datasource, isOpen, form]);

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
      await floConsoleService.datasourcesService.updateDatasource(
        datasource.id,
        data.name,
        data.type,
        parsedConfig,
        data.description?.trim() || undefined
      );

      notifySuccess('Datasource updated successfully');

      if (onSuccess) {
        onSuccess();
      }

      onOpenChange(false);
    } catch (error) {
      console.error('Error updating datasource:', error);
      const errorMessage = extractErrorMessage(error);
      notifyError(errorMessage || 'Failed to update datasource');
    }
  };

  if (!appId) {
    return null;
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit Datasource</DialogTitle>
          {/* <DialogDescription>Update datasource configuration for {currentApp.app_name}</DialogDescription> */}
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
                    <FormMessage />
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
                    <FormMessage />
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
                  <FormMessage />
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
                Save Changes
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default EditDatasourceDialog;
