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
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@app/components/ui/form';
import { Input } from '@app/components/ui/input';
import { Select, SelectContent, SelectTrigger, SelectValue } from '@app/components/ui/select';
import { extractErrorMessage } from '@app/lib/utils';
import { useNotifyStore } from '@app/store';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import ConnectionFields from './ConnectionFields';
import DatasourceTypeOptions from './DatasourceTypeOptions';
import { CONFIG_FIELDS, ConfigValues, defaultConfigValues, valuesToConfig } from './datasource-config';
import { DATASOURCE_TYPES, isFileStorageType } from './datasource-types';
import { createDatasourceSchema, type CreateDatasourceInput, type DatasourceTypeValue } from './schemas';

interface CreateDatasourceDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  onSuccess?: () => void;
}

const DEFAULT_TYPE: DatasourceTypeValue = 'postgres';

const CreateDatasourceDialog: React.FC<CreateDatasourceDialogProps> = ({ isOpen, onOpenChange, appId, onSuccess }) => {
  const navigate = useNavigate();
  const { notifySuccess, notifyError } = useNotifyStore();

  const form = useForm<CreateDatasourceInput>({
    resolver: zodResolver(createDatasourceSchema),
    defaultValues: { name: '', type: DEFAULT_TYPE, description: '' },
  });
  const datasourceType = form.watch('type');

  const [configValues, setConfigValues] = useState<ConfigValues>(() => defaultConfigValues(DEFAULT_TYPE));
  const [configErrors, setConfigErrors] = useState<Record<string, string>>({});

  // A new type starts from its own defaults.
  useEffect(() => {
    setConfigValues(defaultConfigValues(datasourceType));
    setConfigErrors({});
  }, [datasourceType]);

  // Start fresh each time the dialog opens.
  useEffect(() => {
    if (!isOpen) {
      form.reset({ name: '', type: DEFAULT_TYPE, description: '' });
      setConfigValues(defaultConfigValues(DEFAULT_TYPE));
      setConfigErrors({});
    }
  }, [isOpen, form]);

  const setConfigValue = (key: string, value: string | boolean) => {
    setConfigValues((current) => ({ ...current, [key]: value }));
    setConfigErrors((current) => {
      if (!current[key]) return current;
      const next = { ...current };
      delete next[key];
      return next;
    });
  };

  const onSubmit = async (data: CreateDatasourceInput) => {
    const { config, errors } = valuesToConfig(data.type, configValues);
    setConfigErrors(errors);
    if (!config) return;

    try {
      const response = await floConsoleService.datasourcesService.createDatasource(
        data.name.trim(),
        data.type,
        config,
        data.description?.trim() || undefined
      );
      const responseData = response.data?.data as { datasource_id?: string } | undefined;
      notifySuccess('Datasource created successfully');
      onSuccess?.();
      onOpenChange(false);
      if (responseData?.datasource_id) {
        navigate(`/apps/${appId}/datasources/${responseData.datasource_id}`);
      }
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to create datasource');
    }
  };

  if (!appId) {
    return null;
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-2xl min-w-0 overflow-y-auto lg:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Create datasource</DialogTitle>
          <DialogDescription>
            The connection is tested when you create it, so check the details before saving.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-6">
            <section className="flex flex-col gap-4">
              <div className="grid grid-cols-1 gap-x-5 gap-y-4 sm:grid-cols-2">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Name<span className="ml-0.5 text-red-500">*</span>
                      </FormLabel>
                      <FormControl>
                        <Input placeholder="Orders database" {...field} />
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
                      <FormLabel>Type</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select a type" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <DatasourceTypeOptions types={DATASOURCE_TYPES} />
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
                      Description <span className="frost-text-subtle font-normal">(optional)</span>
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="What this datasource holds" {...field} />
                    </FormControl>
                  </FormItem>
                )}
              />
            </section>

            <section className="border-frost-border flex flex-col gap-4 border-t pt-5">
              <div>
                <h3 className="frost-text text-sm font-semibold">Connection</h3>
                {isFileStorageType(datasourceType) ? (
                  <p className="frost-text-muted text-xs">
                    The bucket and credentials can&apos;t be changed after creating it, only the name and description.
                  </p>
                ) : null}
              </div>
              {/* Keyed by type so a switch starts the fields (and their "More settings") afresh. */}
              <ConnectionFields
                key={datasourceType}
                fields={CONFIG_FIELDS[datasourceType]}
                values={configValues}
                errors={configErrors}
                onChange={setConfigValue}
              />
            </section>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={form.formState.isSubmitting}>
                Create datasource
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateDatasourceDialog;
