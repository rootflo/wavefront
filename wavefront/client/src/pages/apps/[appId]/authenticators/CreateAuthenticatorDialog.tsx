import floConsoleService from '@app/api';
import { Button } from '@app/components/ui/button';
import { Checkbox } from '@app/components/ui/checkbox';
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
import {
  cleanParameters,
  getAuthenticatorTypeOptions,
  getProviderConfig,
  initializeParameters,
} from '@app/config/authenticators';
import { useDashboardStore, useNotifyStore } from '@app/store';
import { AuthenticatorType } from '@app/types/authenticator';
import { zodResolver } from '@hookform/resolvers/zod';
import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { z } from 'zod';

const createAuthenticatorSchema = z.object({
  authName: z.string().min(1, 'Authenticator name is required'),
  authType: z.enum(['google_oauth', 'microsoft_oauth', 'email_password']),
  authDesc: z.string().optional(),
});

type CreateAuthenticatorInput = z.infer<typeof createAuthenticatorSchema>;

interface CreateAuthenticatorDialogProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  appId: string;
  onSuccess?: () => void;
}

const CreateAuthenticatorDialog: React.FC<CreateAuthenticatorDialogProps> = ({
  isOpen,
  onOpenChange,
  appId,
  onSuccess,
}) => {
  const navigate = useNavigate();
  const { notifySuccess, notifyError } = useNotifyStore();
  const { selectedApp } = useDashboardStore();
  const [authType, setAuthType] = useState<AuthenticatorType>('google_oauth');
  const [parameters, setParameters] = useState<Record<string, any>>(() => initializeParameters(authType));
  const [loading, setLoading] = useState(false);

  const form = useForm<CreateAuthenticatorInput>({
    resolver: zodResolver(createAuthenticatorSchema),
    defaultValues: {
      authName: '',
      authType: 'google_oauth',
      authDesc: '',
    },
  });

  // Reset parameters when auth type changes
  const watchedAuthType = form.watch('authType');
  useEffect(() => {
    if (isOpen && watchedAuthType) {
      const newType = watchedAuthType as AuthenticatorType;
      setAuthType(newType);
      setParameters(initializeParameters(newType));
    }
  }, [watchedAuthType, isOpen]);

  // Reset form when dialog closes
  useEffect(() => {
    if (!isOpen) {
      form.reset({
        authName: '',
        authType: 'google_oauth',
        authDesc: '',
      });
      setAuthType('google_oauth');
      setParameters(initializeParameters('google_oauth'));
    }
  }, [isOpen, form]);

  const setParameter = (key: string, value: any) => {
    setParameters((prev) => ({ ...prev, [key]: value }));
  };

  const setNestedParameter = (parentKey: string, childKey: string, value: any) => {
    setParameters((prev) => ({
      ...prev,
      [parentKey]: {
        ...prev[parentKey],
        [childKey]: value,
      },
    }));
  };

  const onSubmit = async (data: CreateAuthenticatorInput) => {
    // Validate required fields in config
    const config = getProviderConfig(data.authType);
    if (config) {
      const missingFields: string[] = [];
      Object.entries(config.parameters).forEach(([key, paramConfig]) => {
        if (!paramConfig.required) return;
        const value = parameters[key];
        if (paramConfig.type === 'object' && paramConfig.fields) {
          // Check nested required fields
          Object.entries(paramConfig.fields).forEach(([nestedKey, nestedConfig]) => {
            if (!nestedConfig.required) return;
            const nestedValue = value?.[nestedKey];
            const nestedMissing =
              nestedValue === undefined ||
              nestedValue === null ||
              (Array.isArray(nestedValue) && nestedValue.length === 0) ||
              (typeof nestedValue === 'string' && nestedValue.trim() === '');
            if (nestedMissing) {
              missingFields.push(`${key}.${nestedKey}`);
            }
          });
        } else {
          const isMissing =
            value === undefined ||
            value === null ||
            (Array.isArray(value) && value.length === 0) ||
            (typeof value === 'string' && value.trim() === '');
          if (isMissing) {
            missingFields.push(key);
          }
        }
      });
      if (missingFields.length > 0) {
        notifyError(`Missing required fields: ${missingFields.join(', ')}`);
        return;
      }
    }

    setLoading(true);
    try {
      const response = await floConsoleService.authenticatorService.createAuthenticator({
        auth_name: data.authName.trim(),
        auth_type: data.authType,
        auth_desc: data.authDesc?.trim() || null,
        config: cleanParameters(parameters),
      });

      if (response.data?.meta?.status === 'success') {
        notifySuccess('Authenticator created successfully');

        if (onSuccess) {
          onSuccess();
        }

        onOpenChange(false);

        // Optionally navigate to the created authenticator if we have the ID
        if (response.data?.data?.authenticator?.auth_id) {
          navigate(`/apps/${appId}/authenticators/${response.data.data.authenticator.auth_id}`);
        }
      }
    } catch (error: any) {
      console.error('Error creating authenticator:', error);
      const errorMessage = error?.response?.data?.meta?.error || error?.message || 'Failed to create authenticator';
      notifyError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const renderParameterField = (key: string) => {
    const config = getProviderConfig(authType);
    if (!config) return null;

    const paramConfig = config.parameters[key];
    if (!paramConfig) return null;

    // Handle nested object parameters
    if (paramConfig.type === 'object' && paramConfig.fields) {
      return (
        <div className="col-span-2 space-y-4 rounded-lg border border-gray-200 bg-gray-50 p-4">
          <label className="block text-sm font-medium text-gray-700">
            {key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
            {paramConfig.required && <span className="text-red-500">*</span>}
          </label>
          {paramConfig.description && <p className="text-xs text-gray-500">{paramConfig.description}</p>}
          <div className="grid grid-cols-2 gap-3">
            {Object.entries(paramConfig.fields).map(([nestedKey, nestedConfig]) => (
              <div key={nestedKey}>
                <label className="mb-1 block text-xs font-medium text-gray-700">
                  {nestedKey.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
                  {nestedConfig.required && <span className="text-red-500">*</span>}
                </label>
                {nestedConfig.description && <p className="mb-1 text-xs text-gray-500">{nestedConfig.description}</p>}
                {renderNestedField(key, nestedKey, nestedConfig)}
              </div>
            ))}
          </div>
        </div>
      );
    }

    // Handle array parameters
    if (paramConfig.type === 'array') {
      const arrayValue = Array.isArray(parameters[key]) ? parameters[key].join(', ') : '';
      return (
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            {key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
            {paramConfig.required && <span className="text-red-500">*</span>}
          </label>
          {paramConfig.description && <p className="mb-1 text-xs text-gray-500">{paramConfig.description}</p>}
          <Input
            value={arrayValue}
            onChange={(e) => {
              const values = e.target.value
                .split(',')
                .map((v) => v.trim())
                .filter(Boolean);
              setParameter(key, values);
            }}
            placeholder={paramConfig.placeholder}
          />
          <p className="mt-1 text-xs text-gray-500">Separate multiple values with commas</p>
        </div>
      );
    }

    // Handle boolean parameters
    if (paramConfig.type === 'boolean') {
      return (
        <div className="flex items-center gap-3">
          <Checkbox checked={parameters[key] || false} onCheckedChange={(checked) => setParameter(key, checked)} />
          <div>
            <label className="text-sm font-medium text-gray-700">
              {key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
              {paramConfig.required && <span className="text-red-500">*</span>}
            </label>
            {paramConfig.description && <p className="text-xs text-gray-500">{paramConfig.description}</p>}
          </div>
        </div>
      );
    }

    // Handle number parameters
    if (paramConfig.type === 'number') {
      return (
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            {key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
            {paramConfig.required && <span className="text-red-500">*</span>}
          </label>
          {paramConfig.description && <p className="mb-1 text-xs text-gray-500">{paramConfig.description}</p>}
          <Input
            type="number"
            value={parameters[key] || ''}
            onChange={(e) => setParameter(key, e.target.value ? Number(e.target.value) : '')}
            min={paramConfig.min}
            max={paramConfig.max}
            step={paramConfig.step}
            placeholder={paramConfig.placeholder}
          />
        </div>
      );
    }

    // Handle select parameters
    if (paramConfig.type === 'select' && paramConfig.options) {
      return (
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            {key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
            {paramConfig.required && <span className="text-red-500">*</span>}
          </label>
          {paramConfig.description && <p className="mb-1 text-xs text-gray-500">{paramConfig.description}</p>}
          <Select value={String(parameters[key] || '')} onValueChange={(value) => setParameter(key, value)}>
            <SelectTrigger>
              <SelectValue placeholder="Select an option" />
            </SelectTrigger>
            <SelectContent>
              {paramConfig.options.map((option) => (
                <SelectItem key={String(option.value)} value={String(option.value)}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      );
    }

    // Default: string input
    return (
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">
          {key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
          {paramConfig.required && <span className="text-red-500">*</span>}
        </label>
        {paramConfig.description && <p className="mb-1 text-xs text-gray-500">{paramConfig.description}</p>}
        <Input
          type="text"
          value={parameters[key] || ''}
          onChange={(e) => setParameter(key, e.target.value)}
          placeholder={paramConfig.placeholder}
        />
      </div>
    );
  };

  const renderNestedField = (parentKey: string, childKey: string, config: any) => {
    const value = parameters[parentKey]?.[childKey];

    if (config.type === 'boolean') {
      return (
        <Checkbox
          checked={value || false}
          onCheckedChange={(checked) => setNestedParameter(parentKey, childKey, checked)}
        />
      );
    }

    if (config.type === 'number') {
      return (
        <Input
          type="number"
          value={value || ''}
          onChange={(e) => setNestedParameter(parentKey, childKey, e.target.value ? Number(e.target.value) : '')}
          min={config.min}
          max={config.max}
          step={config.step}
        />
      );
    }

    return (
      <Input
        type="text"
        value={value || ''}
        onChange={(e) => setNestedParameter(parentKey, childKey, e.target.value)}
        placeholder={config.placeholder}
      />
    );
  };

  const config = getProviderConfig(authType);

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create New Authenticator</DialogTitle>
          <DialogDescription>Configure a new authentication provider for {selectedApp?.app_name}</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <div className="grid grid-cols-2 gap-6">
              <FormField
                control={form.control}
                name="authName"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Authenticator Name<span className="text-red-500">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="e.g., Google OAuth Corporate" maxLength={100} {...field} />
                    </FormControl>
                    <FormDescription>{field.value?.length || 0}/100 characters</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="authType"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Authentication Type<span className="text-red-500">*</span>
                    </FormLabel>
                    <Select
                      onValueChange={(value) => {
                        field.onChange(value);
                        const newType = value as AuthenticatorType;
                        setAuthType(newType);
                        setParameters(initializeParameters(newType));
                      }}
                      value={field.value}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select authentication type" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {getAuthenticatorTypeOptions().map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
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
              name="authDesc"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description</FormLabel>
                  <FormControl>
                    <textarea
                      placeholder="Optional description for this authenticator"
                      rows={3}
                      maxLength={500}
                      className="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring flex min-h-[80px] w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>{field.value?.length || 0}/500 characters</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Configuration Parameters */}
            {config && (
              <div className="space-y-4 rounded-lg border border-gray-200 bg-white p-6">
                <h3 className="text-lg font-semibold text-gray-900">Configuration</h3>
                <div className="grid grid-cols-2 gap-4">
                  {Object.keys(config.parameters).map((key) => (
                    <div key={key}>{renderParameterField(key)}</div>
                  ))}
                </div>
              </div>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={loading || form.formState.isSubmitting}>
                Create Authenticator
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default CreateAuthenticatorDialog;
