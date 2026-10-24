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
import { Datasource } from '@app/types/datasource';
import { zodResolver } from '@hookform/resolvers/zod';
import { Lock } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import ConnectionFields from './ConnectionFields';
import DatasourceTypeOptions from './DatasourceTypeOptions';
import { CONFIG_FIELDS, ConfigValues, configToValues, defaultConfigValues, valuesToConfig } from './datasource-config';
import { DATASOURCE_TYPES, isFileStorageType } from './datasource-types';
import { createDatasourceSchema, type CreateDatasourceInput, type DatasourceTypeValue } from './schemas';

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
  // File storage datasources only allow renaming; SQL ones can't become file storage.
  const isFileStorage = isFileStorageType(datasource.type);
  const savedType = datasource.type as DatasourceTypeValue;
  const typeOptions = isFileStorage
    ? DATASOURCE_TYPES.filter((type) => type.value === datasource.type)
    : DATASOURCE_TYPES.filter((type) => !isFileStorageType(type.value));

  const form = useForm<CreateDatasourceInput>({
    resolver: zodResolver(createDatasourceSchema),
    defaultValues: { name: '', type: savedType, description: '' },
  });
  const datasourceType = form.watch('type');

  const [configValues, setConfigValues] = useState<ConfigValues>({});
  const [configErrors, setConfigErrors] = useState<Record<string, string>>({});

  // Fill the form from the saved datasource each time the dialog opens.
  useEffect(() => {
    if (!isOpen) return;
    form.reset({
      name: datasource.name || '',
      type: savedType,
      description: datasource.description || '',
    });
    setConfigValues(configToValues(savedType, datasource.config || {}));
    setConfigErrors({});
  }, [datasource, isOpen, form, savedType]);

  // Switching type starts from that type's defaults; switching back restores the saved settings.
  const handleTypeChange = (value: string, onChange: (value: string) => void) => {
    onChange(value);
    const type = value as DatasourceTypeValue;
    setConfigValues(type === savedType ? configToValues(type, datasource.config || {}) : defaultConfigValues(type));
    setConfigErrors({});
  };

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
    let config: Record<string, unknown>;
    if (isFileStorage) {
      // The backend refuses any change to a file storage config, so it goes back exactly as saved.
      config = datasource.config || {};
    } else {
      const built = valuesToConfig(data.type, configValues);
      setConfigErrors(built.errors);
      if (!built.config) return;
      // Same type: keep any saved keys this form doesn't show, so saving never silently drops them.
      const known = new Set(CONFIG_FIELDS[data.type].map((field) => field.key));
      const extras =
        data.type === savedType
          ? Object.fromEntries(Object.entries(datasource.config || {}).filter(([key]) => !known.has(key)))
          : {};
      config = { ...extras, ...built.config };
    }

    try {
      await floConsoleService.datasourcesService.updateDatasource(
        datasource.id,
        data.name.trim(),
        data.type,
        config,
        data.description?.trim() || undefined
      );
      notifySuccess('Datasource updated successfully');
      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      notifyError(extractErrorMessage(error) || 'Failed to update datasource');
    }
  };

  if (!appId) {
    return null;
  }

  const fieldsType = datasourceType || savedType;

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-2xl min-w-0 overflow-y-auto lg:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Edit datasource</DialogTitle>
          <DialogDescription>
            {isFileStorage
              ? 'Only the name and description can change for file storage.'
              : 'Changing the connection tests it again before saving.'}
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
                      <Select
                        onValueChange={(value) => handleTypeChange(value, field.onChange)}
                        value={field.value}
                        disabled={isFileStorage}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select a type" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <DatasourceTypeOptions types={typeOptions} />
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
                      Description <span className="frost-text-subtle font-normal">(optional)</span>
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="What this datasource holds" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </section>

            <section className="border-frost-border flex flex-col gap-4 border-t pt-5">
              <div className="flex items-center gap-2">
                <h3 className="frost-text text-sm font-semibold">Connection</h3>
                {isFileStorage ? (
                  <span className="frost-text-muted inline-flex items-center gap-1 text-xs">
                    <Lock className="size-3" />
                    Read-only: delete and recreate the datasource to change it
                  </span>
                ) : null}
              </div>
              {CONFIG_FIELDS[fieldsType] ? (
                <ConnectionFields
                  key={`${fieldsType}-${isOpen}`}
                  fields={CONFIG_FIELDS[fieldsType]}
                  values={configValues}
                  errors={configErrors}
                  onChange={setConfigValue}
                  readOnly={isFileStorage}
                />
              ) : null}
            </section>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={form.formState.isSubmitting}>
                Save changes
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default EditDatasourceDialog;
